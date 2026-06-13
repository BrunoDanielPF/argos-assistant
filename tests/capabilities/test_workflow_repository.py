from datetime import datetime, timedelta, timezone

import pytest

from assistant.capabilities.workflow_repository import (
    CapabilityWorkflowRecord,
    CapabilityWorkflowRepository,
    PendingWorkflowLimit,
)


def build_record(
    now: datetime,
    *,
    workflow_id: str = "workflow-1",
    proposal_id: str = "proposal-1",
    session_id: str = "default",
    status: str = "WAITING_TOOL_APPROVAL",
) -> CapabilityWorkflowRecord:
    return CapabilityWorkflowRecord(
        workflow_id=workflow_id,
        proposal_id=proposal_id,
        session_id=session_id,
        run_id="run-1",
        requested_capability="file.metadata.stat",
        tool_name="file.metadata.stat",
        tool_version="1.0.0",
        tool_definition_hash="hash-1",
        proposal={"status": "proposed"},
        original_action={
            "mode": "action",
            "capability": "file.metadata.stat",
            "arguments": {"path": "notes.txt"},
        },
        status=status,
        retry_status="pending",
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
        expires_at=(now + timedelta(hours=24)).isoformat(),
    )


def test_repository_persists_workflow_and_lists_pending(tmp_path):
    now = datetime(2026, 6, 13, tzinfo=timezone.utc)
    repository = CapabilityWorkflowRepository(
        tmp_path / "argos.db",
        now_fn=lambda: now,
    )
    record = build_record(now)

    repository.create(record)

    loaded = repository.load(record.workflow_id)
    pending = repository.list_pending(session_id="default")

    assert loaded == record
    assert pending == [record]
    repository.close()


def test_repository_rejects_more_than_session_pending_limit(tmp_path):
    now = datetime(2026, 6, 13, tzinfo=timezone.utc)
    repository = CapabilityWorkflowRepository(
        tmp_path / "argos.db",
        max_pending_per_session=2,
        now_fn=lambda: now,
    )
    repository.create(build_record(now, workflow_id="w1", proposal_id="p1"))
    repository.create(build_record(now, workflow_id="w2", proposal_id="p2"))

    with pytest.raises(PendingWorkflowLimit):
        repository.create(
            build_record(now, workflow_id="w3", proposal_id="p3")
        )

    repository.close()


def test_retry_claim_is_compare_and_set(tmp_path):
    now = datetime(2026, 6, 13, tzinfo=timezone.utc)
    repository = CapabilityWorkflowRepository(
        tmp_path / "argos.db",
        now_fn=lambda: now,
    )
    repository.create(
        build_record(now, status="WAITING_RETRY_CONFIRMATION")
    )

    first = repository.claim_retry("workflow-1")
    duplicate = repository.claim_retry("workflow-1")
    completed = repository.complete_retry(
        "workflow-1",
        status="executed",
        result={"ok": True},
    )

    assert first is True
    assert duplicate is False
    assert completed is True
    loaded = repository.load("workflow-1")
    assert loaded.retry_status == "executed"
    assert loaded.execution_result == {"ok": True}
    repository.close()


def test_repository_returns_expired_pending_workflows(tmp_path):
    now = datetime(2026, 6, 13, tzinfo=timezone.utc)
    repository = CapabilityWorkflowRepository(
        tmp_path / "argos.db",
        now_fn=lambda: now,
    )
    expired = build_record(now, workflow_id="expired", proposal_id="p-expired")
    expired = expired.model_copy(
        update={"expires_at": (now - timedelta(seconds=1)).isoformat()}
    )
    repository.create(expired)
    repository.create(build_record(now, workflow_id="active", proposal_id="p2"))

    assert [
        item.workflow_id for item in repository.list_expired(now=now)
    ] == ["expired"]
    repository.close()


def test_tool_lease_has_single_owner_until_expiry(tmp_path):
    now = datetime(2026, 6, 13, tzinfo=timezone.utc)
    current = {"value": now}
    repository = CapabilityWorkflowRepository(
        tmp_path / "argos.db",
        now_fn=lambda: current["value"],
    )
    expiry = now + timedelta(minutes=5)

    assert repository.acquire_tool_lease(
        "file.metadata.stat@1.0.0",
        "workflow-1",
        expires_at=expiry,
    )
    assert not repository.acquire_tool_lease(
        "file.metadata.stat@1.0.0",
        "workflow-2",
        expires_at=expiry,
    )

    current["value"] = expiry + timedelta(seconds=1)
    assert repository.acquire_tool_lease(
        "file.metadata.stat@1.0.0",
        "workflow-2",
        expires_at=current["value"] + timedelta(minutes=5),
    )
    assert not repository.release_tool_lease(
        "file.metadata.stat@1.0.0",
        "workflow-1",
    )
    assert repository.release_tool_lease(
        "file.metadata.stat@1.0.0",
        "workflow-2",
    )
    repository.close()
