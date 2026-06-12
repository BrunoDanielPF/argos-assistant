from assistant.capabilities.registry import (
    CapabilityRegistry,
    build_default_registry,
)
from assistant.execution.policy import decide_policy
from assistant.recovery.models import (
    FailureEvent,
    FailureType,
    RecoveryDecision,
    RecoveryRisk,
)


class RecoveryPolicy:
    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
    ) -> None:
        self._registry = registry or build_default_registry()

    def decide_action(
        self,
        capability: str,
        arguments: dict,
    ) -> RecoveryDecision:
        validation = self._registry.validate(capability, arguments)
        if not validation.ok:
            return RecoveryDecision(
                allowed=False,
                requires_confirmation=False,
                risk=RecoveryRisk.MEDIUM,
                reason=validation.error_code or "invalid_action",
            )

        assert validation.capability is not None
        assert validation.arguments is not None
        canonical = validation.capability.name
        policy = decide_policy(
            canonical,
            validation.arguments,
            registry=self._registry,
        )
        if policy == "blocked":
            return RecoveryDecision(
                allowed=False,
                requires_confirmation=False,
                risk=RecoveryRisk.CRITICAL,
                reason="policy_blocked",
            )
        if policy == "allow":
            return RecoveryDecision(
                allowed=True,
                requires_confirmation=False,
                risk=RecoveryRisk.LOW,
                reason="read_only_action",
            )
        return RecoveryDecision(
            allowed=True,
            requires_confirmation=True,
            risk=(
                RecoveryRisk.HIGH
                if canonical in {"file.delete_one", "file.move_many"}
                else RecoveryRisk.MEDIUM
            ),
            reason="sensitive_action_requires_confirmation",
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
        if (
            strategy == "retry_with_backoff"
            and event.failure_type == FailureType.TIMEOUT
            and attempt < 1
            and event.source == "tool"
            and event.metadata.get("retry_safe") is True
        ):
            return RecoveryDecision(
                allowed=True,
                requires_confirmation=False,
                risk=RecoveryRisk.LOW,
                reason="one_safe_tool_timeout_retry_allowed",
            )

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
            and action_decision.risk == RecoveryRisk.LOW
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
