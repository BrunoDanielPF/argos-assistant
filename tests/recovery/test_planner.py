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


def test_no_results_is_a_normal_empty_outcome():
    event = FailureEvent(
        source="tool",
        operation="files.search",
        failure_type=FailureType.NO_RESULTS,
        message="No files matched",
    )

    plan = RecoveryPlanner().create_plan(event, arguments={"pattern": "*.tmp"})

    assert plan.strategy == RecoveryStrategy.FALLBACK_TO_PARTIAL_ANSWER
    assert plan.requires_confirmation is False
    assert "nenhum resultado" in plan.user_message.lower()


def test_unsupported_capability_explains_limitation_and_alternative():
    event = FailureEvent(
        source="action",
        operation="shell.run",
        failure_type=FailureType.UNSUPPORTED_CAPABILITY,
        message="Unsupported capability: shell.run",
    )

    plan = RecoveryPlanner().create_plan(event, arguments={"command": "dir"})

    assert plan.strategy == RecoveryStrategy.SUGGEST_SAFE_ALTERNATIVE
    assert plan.requires_confirmation is False
    assert "nao oferece suporte" in plan.user_message.lower()
    assert "alternativa" in plan.user_message.lower()


def test_invalid_schema_can_propose_a_corrected_plan():
    event = FailureEvent(
        source="action",
        operation="file.write",
        failure_type=FailureType.INVALID_SCHEMA,
        message="mode is required",
    )

    plan = RecoveryPlanner().create_plan(event, arguments={"path": "notes.txt"})

    assert plan.strategy == RecoveryStrategy.REBUILD_CONTEXT
    assert plan.requires_confirmation is False
    assert "corrigido" in plan.user_message.lower()


def test_wrong_intent_with_side_effect_requires_new_confirmation():
    event = FailureEvent(
        source="planner",
        operation="file.move_many",
        failure_type=FailureType.WRONG_INTENT,
        message="Intent was modify_path",
    )

    plan = RecoveryPlanner().create_plan(
        event,
        arguments={"source_root": ".", "pattern": "*.txt", "destination": "backup"},
    )

    assert plan.strategy == RecoveryStrategy.DRY_RUN_THEN_CONFIRM
    assert plan.requires_confirmation is True
