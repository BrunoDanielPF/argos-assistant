from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from assistant.capabilities.definitions import ToolDefinition
from assistant.capabilities.generated_tool_policy import (
    GeneratedToolSafetyPolicy,
)
from assistant.capabilities.templates import (
    SafeToolTemplateCatalog,
    ToolDefinitionSource,
)
from assistant.tools.audit import ToolAuditEvent, ToolAuditLog
from assistant.tools.generator import GeneratedToolDraft, ToolDraftGenerator
from assistant.tools.installer import ToolInstaller
from assistant.tools.models import ToolPermissions
from assistant.tools.state import ToolStateStore
from assistant.workflows.policies import is_destructive_shell_command


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CapabilityProvisioningProposal(StrictModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    status: Literal["proposed", "blocked", "unsupported"]
    requested_capability: str
    user_goal: str
    arguments: dict = Field(default_factory=dict)
    platform_context: dict = Field(default_factory=dict)
    original_action: dict = Field(default_factory=dict)
    definition: ToolDefinition | None = None
    tool_definition_hash: str | None = None
    reason: str | None = None

    @property
    def can_create(self) -> bool:
        return self.status == "proposed" and self.definition is not None


class EnabledProvisionedTool(StrictModel):
    proposal_id: str
    tool_name: str
    tool_version: str
    state: Literal["enabled"]
    installed_path: Path
    original_action: dict
    permissions: ToolPermissions = Field(default_factory=ToolPermissions)


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
        state_store: ToolStateStore,
        installer: ToolInstaller,
        audit_log: ToolAuditLog | None = None,
        definition_sources: list[ToolDefinitionSource] | None = None,
        generated_tool_policy: GeneratedToolSafetyPolicy | None = None,
    ) -> None:
        self._generator = generator
        self._state_store = state_store
        self._installer = installer
        self._audit_log = audit_log
        self._definition_sources = (
            list(definition_sources)
            if definition_sources is not None
            else [SafeToolTemplateCatalog()]
        )
        self._generated_tool_policy = (
            generated_tool_policy or GeneratedToolSafetyPolicy()
        )

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

        definition = None
        for source in self._definition_sources:
            definition = source.build_candidate(
                requested_capability=requested_capability,
                user_goal=user_goal,
                arguments=arguments,
                platform_context=platform_context,
                original_action=original_action,
            )
            if definition is not None:
                if getattr(source, "source_kind", None) == "model":
                    decision = self._generated_tool_policy.evaluate(
                        definition
                    )
                    if not decision.allowed:
                        return CapabilityProvisioningProposal(
                            status="blocked",
                            requested_capability=requested_capability,
                            user_goal=user_goal,
                            arguments=arguments,
                            platform_context=platform_context,
                            original_action=original_action,
                            reason=(
                                "generated_tool_unsafe:"
                                + ",".join(decision.reasons)
                            ),
                        )
                break
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
            tool_definition_hash=definition.definition_hash(),
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

    def approve_install_enable(
        self,
        *,
        proposal: CapabilityProvisioningProposal,
        draft_path: Path,
    ) -> EnabledProvisionedTool:
        if proposal.definition is None:
            raise ValueError("proposal has no tool definition")
        definition = proposal.definition
        record = self._state_store.get(
            definition.name,
            definition.version,
        )
        if record is None or record.state != "validated":
            raise ValueError(
                f"{definition.name}@{definition.version} is not validated"
            )

        self._state_store.transition(
            definition.name,
            definition.version,
            "approved",
        )
        self._audit("tool_approved", proposal)
        installed_path = self._installer.install(Path(draft_path))
        self._audit(
            "tool_installed",
            proposal,
            {"path": str(installed_path)},
        )
        enabled = self._state_store.transition(
            definition.name,
            definition.version,
            "enabled",
        )
        self._audit("tool_enabled", proposal)
        return EnabledProvisionedTool(
            proposal_id=proposal.proposal_id,
            tool_name=definition.name,
            tool_version=definition.version,
            state=enabled.state,
            installed_path=installed_path,
            original_action=proposal.original_action,
            permissions=definition.permissions,
        )

    def reject_enablement(
        self,
        proposal: CapabilityProvisioningProposal,
    ) -> None:
        self._audit("tool_enablement_rejected", proposal)

    def record_enabled_event(
        self,
        event: str,
        enabled: EnabledProvisionedTool,
        details: dict | None = None,
    ) -> None:
        if self._audit_log is None:
            return
        self._audit_log.write(
            ToolAuditEvent(
                event=event,
                invocation_id=enabled.proposal_id,
                tool_name=enabled.tool_name,
                tool_version=enabled.tool_version,
                details=details or {},
            )
        )

    @staticmethod
    def build_retry_action(enabled: EnabledProvisionedTool) -> dict:
        original_arguments = enabled.original_action.get("arguments")
        arguments = (
            dict(original_arguments)
            if isinstance(original_arguments, dict)
            else {}
        )
        if enabled.tool_name == "local.windows.env_set_user":
            arguments = {
                key: arguments[key]
                for key in ("name", "value")
                if key in arguments
            }
        elif enabled.tool_name == "local.git.status":
            context = enabled.original_action.get("context")
            if isinstance(context, dict) and context.get("current_cwd"):
                arguments = {"cwd": context["current_cwd"]}
            else:
                arguments = {}
        return {
            "mode": "action",
            "capability": enabled.tool_name,
            "arguments": arguments,
        }

    @staticmethod
    def summarize_permissions(
        enabled: EnabledProvisionedTool,
    ) -> list[str]:
        summary = []
        if enabled.tool_name == "local.windows.env_set_user":
            summary.append("windows_registry:user_environment")
        filesystem = enabled.permissions.filesystem
        summary.append(
            "filesystem_write:none"
            if not filesystem.write
            else f"filesystem_write:{','.join(filesystem.write)}"
        )
        network = enabled.permissions.network
        summary.append(
            "network:none"
            if not network.enabled
            else f"network:{','.join(network.hosts)}"
        )
        subprocess = enabled.permissions.subprocess.executables
        summary.append(
            "subprocess:none"
            if not subprocess
            else f"subprocess:{','.join(subprocess)}"
        )
        return summary

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
