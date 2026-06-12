from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from assistant.tools.audit import ToolAuditEvent, ToolAuditLog
from assistant.tools.generator import GeneratedToolDraft, ToolDraftGenerator
from assistant.tools.models import ToolExecution, ToolPermissions
from assistant.workflows.policies import is_destructive_shell_command


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolDefinition(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*)+$")
    version: str = Field(
        default="1.0.0",
        pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$",
    )
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    input_schema: dict
    output_schema: dict
    permissions: ToolPermissions = Field(default_factory=ToolPermissions)
    execution: ToolExecution = Field(
        default_factory=lambda: ToolExecution(
            timeout_seconds=30,
            max_output_bytes=65_536,
        )
    )
    handler_body: str = Field(min_length=1)


class CapabilityProvisioningProposal(StrictModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    status: Literal["proposed", "blocked", "unsupported"]
    requested_capability: str
    user_goal: str
    arguments: dict = Field(default_factory=dict)
    platform_context: dict = Field(default_factory=dict)
    original_action: dict = Field(default_factory=dict)
    definition: ToolDefinition | None = None
    reason: str | None = None

    @property
    def can_create(self) -> bool:
        return self.status == "proposed" and self.definition is not None


class CapabilityProvisioningService:
    _destructive_capability_markers = (
        "delete",
        "destroy",
        "erase",
        "format",
        "remove",
        "shutdown",
        "wipe",
    )

    def __init__(
        self,
        generator: ToolDraftGenerator,
        audit_log: ToolAuditLog | None = None,
    ) -> None:
        self._generator = generator
        self._audit_log = audit_log

    def propose(
        self,
        *,
        requested_capability: str,
        user_goal: str,
        arguments: dict,
        platform_context: dict,
        original_action: dict,
    ) -> CapabilityProvisioningProposal:
        if self._is_destructive(requested_capability, arguments):
            return CapabilityProvisioningProposal(
                status="blocked",
                requested_capability=requested_capability,
                user_goal=user_goal,
                arguments=arguments,
                platform_context=platform_context,
                original_action=original_action,
                reason="destructive_action",
            )

        definition = self._build_definition(
            requested_capability=requested_capability,
            arguments=arguments,
            platform_context=platform_context,
        )
        if definition is None:
            return CapabilityProvisioningProposal(
                status="unsupported",
                requested_capability=requested_capability,
                user_goal=user_goal,
                arguments=arguments,
                platform_context=platform_context,
                original_action=original_action,
                reason="no_safe_template",
            )

        proposal = CapabilityProvisioningProposal(
            status="proposed",
            requested_capability=requested_capability,
            user_goal=user_goal,
            arguments=arguments,
            platform_context=platform_context,
            original_action=original_action,
            definition=definition,
        )
        self._audit("draft_proposed", proposal)
        return proposal

    def create_draft(
        self,
        proposal: CapabilityProvisioningProposal,
    ) -> GeneratedToolDraft:
        if not proposal.can_create or proposal.definition is None:
            raise ValueError(
                proposal.reason or "proposal is not eligible for draft creation"
            )
        try:
            draft = self._generator.generate(
                proposal.definition.model_dump()
            )
        except Exception:
            self._audit("draft_generation_failed", proposal)
            raise
        self._audit(
            "draft_created",
            proposal,
            {
                "path": str(draft.path),
                "state": draft.state,
                "can_execute": draft.can_execute,
            },
        )
        return draft

    def _build_definition(
        self,
        *,
        requested_capability: str,
        arguments: dict,
        platform_context: dict,
    ) -> ToolDefinition | None:
        if requested_capability == "shell.run":
            command = arguments.get("command")
            if (
                isinstance(command, str)
                and " ".join(command.casefold().split()) == "git status"
            ):
                return self._git_status_definition(platform_context)
            return None
        if requested_capability in {
            "modify_environment_variable",
            "windows.env.set_user",
        }:
            return self._windows_env_definition()
        return None

    def _is_destructive(
        self,
        requested_capability: str,
        arguments: dict,
    ) -> bool:
        normalized = requested_capability.casefold()
        if any(
            marker in normalized
            for marker in self._destructive_capability_markers
        ):
            return True
        return (
            requested_capability == "shell.run"
            and is_destructive_shell_command(arguments.get("command"))
        )

    @staticmethod
    def _git_status_definition(platform_context: dict) -> ToolDefinition:
        return ToolDefinition(
            name="local.git.status",
            title="Git Status",
            description=(
                "Executa somente git status em um diretorio local informado."
            ),
            input_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["cwd"],
                "properties": {
                    "cwd": {"type": "string", "minLength": 1},
                },
            },
            output_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["returncode", "stdout", "stderr"],
                "properties": {
                    "returncode": {"type": "integer"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                },
            },
            permissions=ToolPermissions.model_validate(
                {
                    "filesystem": {
                        "read": ["${cwd}/**"],
                        "write": [],
                    },
                    "network": {"enabled": False, "hosts": []},
                    "subprocess": {"executables": ["git"]},
                }
            ),
            execution=ToolExecution(
                timeout_seconds=15,
                max_output_bytes=65_536,
            ),
            handler_body=(
                "import subprocess\n\n"
                "def run(arguments):\n"
                "    completed = subprocess.run(\n"
                "        ['git', 'status'],\n"
                "        cwd=arguments.get('cwd'),\n"
                "        check=False,\n"
                "        capture_output=True,\n"
                "        text=True,\n"
                "        shell=False,\n"
                "    )\n"
                "    return {\n"
                "        'returncode': completed.returncode,\n"
                "        'stdout': completed.stdout,\n"
                "        'stderr': completed.stderr,\n"
                "    }\n"
            ),
        )

    @staticmethod
    def _windows_env_definition() -> ToolDefinition:
        return ToolDefinition(
            name="local.windows.env_set_user",
            title="Set Windows User Environment Variable",
            description=(
                "Define uma variavel de ambiente no escopo do usuario Windows."
            ),
            input_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "value"],
                "properties": {
                    "name": {
                        "type": "string",
                        "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
                    },
                    "value": {"type": "string"},
                },
            },
            output_schema={
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "scope", "updated"],
                "properties": {
                    "name": {"type": "string"},
                    "scope": {"const": "user"},
                    "updated": {"type": "boolean"},
                },
            },
            permissions=ToolPermissions(),
            execution=ToolExecution(
                timeout_seconds=10,
                max_output_bytes=16_384,
            ),
            handler_body=(
                "import winreg\n\n"
                "def run(arguments):\n"
                "    name = arguments['name']\n"
                "    value = arguments['value']\n"
                "    with winreg.OpenKey(\n"
                "        winreg.HKEY_CURRENT_USER,\n"
                "        'Environment',\n"
                "        0,\n"
                "        winreg.KEY_SET_VALUE,\n"
                "    ) as key:\n"
                "        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)\n"
                "    return {'name': name, 'scope': 'user', 'updated': True}\n"
            ),
        )

    def _audit(
        self,
        event: str,
        proposal: CapabilityProvisioningProposal,
        details: dict | None = None,
    ) -> None:
        if self._audit_log is None or proposal.definition is None:
            return
        self._audit_log.write(
            ToolAuditEvent(
                event=event,
                invocation_id=proposal.proposal_id,
                tool_name=proposal.definition.name,
                tool_version=proposal.definition.version,
                details={
                    "requested_capability": proposal.requested_capability,
                    **(details or {}),
                },
            )
        )
