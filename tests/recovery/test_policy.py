from assistant.recovery.models import FailureEvent, FailureType, RecoveryRisk
from assistant.recovery.policy import RecoveryPolicy


def failure(
    failure_type: FailureType,
    operation: str,
    source: str = "test",
) -> FailureEvent:
    return FailureEvent(
        source=source,
        operation=operation,
        failure_type=failure_type,
        message="failed",
    )


def test_policy_allows_one_retry_for_safe_timeout():
    event = failure(FailureType.TIMEOUT, "local.echo", source="tool")
    event.metadata["retry_safe"] = True
    decision = RecoveryPolicy().decide(
        event,
        strategy="retry_with_backoff",
        attempt=0,
        action={"capability": "local.echo", "arguments": {}},
    )

    assert decision.allowed is True
    assert decision.requires_confirmation is False
    assert decision.risk == RecoveryRisk.LOW


def test_policy_blocks_second_automatic_retry():
    event = failure(FailureType.TIMEOUT, "local.echo", source="tool")
    event.metadata["retry_safe"] = True
    decision = RecoveryPolicy().decide(
        event,
        strategy="retry_with_backoff",
        attempt=1,
        action={"capability": "local.echo", "arguments": {}},
    )

    assert decision.allowed is False


def test_policy_does_not_retry_tool_without_read_only_proof():
    decision = RecoveryPolicy().decide(
        failure(FailureType.TIMEOUT, "local.writer", source="tool"),
        strategy="retry_with_backoff",
        attempt=0,
        action={"capability": "local.writer", "arguments": {}},
    )

    assert decision.allowed is False


def test_policy_never_auto_executes_destructive_action():
    decision = RecoveryPolicy().decide(
        failure(FailureType.POLICY_BLOCKED, "delete_files"),
        strategy="dry_run_then_confirm",
        attempt=0,
        action={
            "capability": "delete_files",
            "arguments": {"path": ".", "pattern": "*.tmp"},
        },
    )

    assert decision.allowed is False
    assert decision.requires_confirmation is False
    assert decision.risk == RecoveryRisk.CRITICAL


def test_policy_requires_confirmation_for_path_change():
    decision = RecoveryPolicy().decide_action(
        "modify_path",
        {"value": "C:\\tools"},
    )

    assert decision.allowed is True
    assert decision.requires_confirmation is True
    assert decision.risk == RecoveryRisk.HIGH
