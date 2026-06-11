from assistant.recovery.models import (
    FailureEvent,
    FailureType,
    RecoveryStrategy,
)
from assistant.recovery.planner import RecoveryPlanner


def test_planner_limits_safe_timeout_to_one_retry():
    event = FailureEvent(
        source="tool",
        operation="local.echo",
        failure_type=FailureType.TIMEOUT,
        message="tool timed out",
        metadata={"retry_safe": True},
    )

    plan = RecoveryPlanner().create_plan(event, arguments={"text": "hello"})

    assert plan.strategy == RecoveryStrategy.RETRY_WITH_BACKOFF
    assert plan.max_retries == 1
    assert plan.requires_confirmation is False


def test_planner_uses_safe_alternative_for_policy_block():
    event = FailureEvent(
        source="action",
        operation="delete_files",
        failure_type=FailureType.POLICY_BLOCKED,
        message="Blocked capability: delete_files",
    )

    plan = RecoveryPlanner().create_plan(
        event,
        arguments={"path": ".", "pattern": "*.tmp"},
    )

    assert plan.strategy == RecoveryStrategy.SUGGEST_SAFE_ALTERNATIVE
    assert "bloqueada" in plan.user_message.lower()
