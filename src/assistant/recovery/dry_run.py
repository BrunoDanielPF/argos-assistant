from assistant.recovery.models import DryRunPlan
from assistant.recovery.policy import RecoveryPolicy


class DryRunBuilder:
    def __init__(self, policy: RecoveryPolicy | None = None) -> None:
        self._policy = policy or RecoveryPolicy()

    def build(self, capability: str, arguments: dict) -> DryRunPlan:
        decision = self._policy.decide_action(capability, arguments)
        resources = self._resources(capability, arguments)
        permissions = self._permissions(capability, resources)
        if decision.allowed:
            expected = (
                f"A acao {capability} seria executada sobre "
                f"{', '.join(resources) if resources else 'os recursos informados'}."
            )
        else:
            expected = (
                f"A acao {capability} nao sera executada automaticamente; "
                "apenas uma alternativa segura pode ser sugerida."
            )
        return DryRunPlan(
            action=capability,
            resources_affected=resources,
            risk=decision.risk,
            permissions_required=permissions,
            requires_confirmation=decision.requires_confirmation,
            expected_result=expected,
            can_execute=decision.allowed,
        )

    @staticmethod
    def _resources(capability: str, arguments: dict) -> list[str]:
        resources = []
        for key in ("path", "source", "destination", "root"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip() and value not in resources:
                resources.append(value)
        if capability == "modify_path":
            resources.append("environment:PATH")
        if capability == "modify_environment_variable":
            name = arguments.get("name", "unknown")
            resources.append(f"environment:{name}")
        return resources

    @staticmethod
    def _permissions(capability: str, resources: list[str]) -> list[str]:
        if capability in {"open_file", "search_files", "files.inspect"}:
            return [f"read:{resource}" for resource in resources]
        if capability in {
            "create_file",
            "write_file",
            "files.move",
            "files.write",
            "delete_file",
            "delete_files",
        }:
            return [f"write:{resource}" for resource in resources]
        if capability in {"run_shell_command", "shell.run"}:
            return ["subprocess"]
        if capability == "modify_path":
            return ["environment_write:PATH"]
        if capability == "modify_environment_variable":
            return ["environment_write"]
        if capability in {"install_tool", "tool.install"}:
            return ["filesystem_write", "subprocess"]
        return [f"execute:{capability}"]
