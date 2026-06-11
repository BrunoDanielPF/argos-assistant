from assistant.recovery.classifier import FailureClassifier
from assistant.recovery.models import FailureType


def test_classifier_uses_explicit_error_code():
    event = FailureClassifier().classify(
        source="tool",
        operation="local.echo",
        message="tool timed out",
        error_code="timeout",
    )

    assert event.failure_type == FailureType.TIMEOUT
    assert event.error_code == "timeout"


def test_classifier_detects_policy_block_from_message():
    event = FailureClassifier().classify(
        source="action",
        operation="delete_files",
        message="Blocked capability: delete_files",
    )

    assert event.failure_type == FailureType.POLICY_BLOCKED


def test_classifier_does_not_persist_sensitive_metadata():
    event = FailureClassifier().classify(
        source="tool",
        operation="local.echo",
        message="failed",
        metadata={"token": "secret-value", "path": "C:\\work"},
    )

    assert event.metadata == {"token": "[REDACTED]", "path": "C:\\work"}


def test_classifier_redacts_secret_from_failure_message():
    event = FailureClassifier().classify(
        source="tool",
        operation="local.echo",
        message="request failed token=secret-value",
    )

    assert "secret-value" not in event.message
    assert "[REDACTED]" in event.message
