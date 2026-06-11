from assistant.recovery.models import (
    FailureEvent,
    FailureType,
    RecoveryDecision,
    RecoveryRisk,
)


_READ_ONLY_ACTIONS = {
    "open_file",
    "open_url",
    "search_files",
    "files.inspect",
    "files.suggest_destination",
}
_SENSITIVE_ACTIONS = {
    "create_file",
    "write_file",
    "files.move",
    "files.write",
    "run_shell_command",
    "shell.run",
    "modify_path",
    "modify_environment_variable",
    "modify_config",
    "install_tool",
    "tool.install",
}
_DESTRUCTIVE_ACTIONS = {
    "delete_file",
    "delete_files",
    "destructive_action",
    "format_disk",
    "shutdown_system",
}


class RecoveryPolicy:
    def decide_action(
        self,
        capability: str,
        arguments: dict,
    ) -> RecoveryDecision:
        del arguments
        if capability in _DESTRUCTIVE_ACTIONS:
            return RecoveryDecision(
                allowed=False,
                requires_confirmation=False,
                risk=RecoveryRisk.CRITICAL,
                reason="destructive_actions_are_never_recovered_automatically",
            )
        if capability in _SENSITIVE_ACTIONS:
            return RecoveryDecision(
                allowed=True,
                requires_confirmation=True,
                risk=(
                    RecoveryRisk.HIGH
                    if capability in {"run_shell_command", "shell.run", "modify_path"}
                    else RecoveryRisk.MEDIUM
                ),
                reason="sensitive_action_requires_confirmation",
            )
        if capability in _READ_ONLY_ACTIONS:
            return RecoveryDecision(
                allowed=True,
                requires_confirmation=False,
                risk=RecoveryRisk.LOW,
                reason="read_only_action",
            )
        return RecoveryDecision(
            allowed=True,
            requires_confirmation=True,
            risk=RecoveryRisk.MEDIUM,
            reason="unknown_effect_requires_confirmation",
        )

    def decide(
        self,
        event: FailureEvent,
        *,
        strategy: str,
        attempt: int,
        action: dict | None = None,
    ) -> RecoveryDecision:
        action = action or {}
        capability = str(action.get("capability") or event.operation)
        action_decision = self.decide_action(
            capability,
            action.get("arguments") or {},
        )
        if not action_decision.allowed:
            return action_decision
        if (
            strategy == "retry_with_backoff"
            and event.failure_type == FailureType.TIMEOUT
            and attempt < 1
            and (
                action_decision.risk == RecoveryRisk.LOW
                or (
                    event.source == "tool"
                    and event.metadata.get("retry_safe") is True
                )
            )
        ):
            return RecoveryDecision(
                allowed=True,
                requires_confirmation=False,
                risk=RecoveryRisk.LOW,
                reason="one_safe_timeout_retry_allowed",
            )
        if strategy == "retry_with_backoff":
            return RecoveryDecision(
                allowed=False,
                requires_confirmation=action_decision.requires_confirmation,
                risk=action_decision.risk,
                reason="automatic_retry_not_allowed",
            )
        return action_decision
