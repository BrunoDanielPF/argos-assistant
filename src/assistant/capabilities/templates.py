from __future__ import annotations

from typing import Protocol

from assistant.capabilities.definitions import ToolDefinition
from assistant.tools.models import ToolExecution, ToolPermissions


class ToolDefinitionSource(Protocol):
    def build_candidate(
        self,
        *,
        requested_capability: str,
        user_goal: str,
        arguments: dict,
        platform_context: dict,
        original_action: dict,
    ) -> ToolDefinition | None: ...


class SafeToolTemplateCatalog:
    source_kind = "template"

    def build_candidate(
        self,
        *,
        requested_capability: str,
        user_goal: str,
        arguments: dict,
        platform_context: dict,
        original_action: dict,
    ) -> ToolDefinition | None:
        if requested_capability == "shell.run":
            command = arguments.get("command")
            if (
                isinstance(command, str)
                and " ".join(command.casefold().split()) == "git status"
            ):
                return self._git_status_definition()
            return None
        if requested_capability in {
            "modify_environment_variable",
            "windows.env.set_user",
        }:
            return self._windows_env_definition()
        return None

    @staticmethod
    def _git_status_definition() -> ToolDefinition:
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
