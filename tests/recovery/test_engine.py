import json

from assistant.recovery.engine import RecoveryEngine
from assistant.recovery.models import FailureType, RecoveryStrategy
from assistant.recovery.repository import RecoveryRepository


def test_engine_explains_policy_block_and_suggests_alternative():
    outcome = RecoveryEngine().handle_failure(
        source="action",
        operation="delete_files",
        message="Blocked capability: delete_files",
        arguments={"path": ".", "pattern": "*.tmp"},
    )

    assert outcome.event.failure_type == FailureType.POLICY_BLOCKED
    assert outcome.plan.strategy == RecoveryStrategy.SUGGEST_SAFE_ALTERNATIVE
    assert outcome.plan.requires_confirmation is False
    assert outcome.dry_run is not None
    assert outcome.dry_run.can_execute is False
    assert "bloqueada" in outcome.plan.user_message.lower()


def test_engine_persists_redacted_failure_event(tmp_path):
    repository = RecoveryRepository(tmp_path / "recovery.jsonl")
    engine = RecoveryEngine(repository=repository)

    engine.handle_failure(
        source="tool",
        operation="local.echo",
        message="failed",
        error_code="tool_error",
        metadata={"password": "secret-value", "safe": "visible"},
    )

    content = repository.path.read_text(encoding="utf-8")
    assert "secret-value" not in content
    assert "[REDACTED]" in content
    assert "visible" in content


def test_engine_persists_recovery_attempt(tmp_path):
    repository = RecoveryRepository(tmp_path / "recovery.jsonl")
    engine = RecoveryEngine(repository=repository)
    outcome = engine.handle_failure(
        source="tool",
        operation="local.echo",
        message="tool timed out",
        error_code="timeout",
        metadata={"retry_safe": True},
    )

    engine.record_attempt(
        outcome,
        attempt=1,
        succeeded=False,
        message="tool timed out",
    )

    records = [
        json.loads(line)
        for line in repository.path.read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["record_type"] == "recovery_outcome"
    assert records[1]["record_type"] == "recovery_attempt"
    assert records[1]["attempt"]["failure_event_id"] == outcome.event.id
