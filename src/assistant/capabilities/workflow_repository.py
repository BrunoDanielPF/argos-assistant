from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Callable

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PendingWorkflowLimit(RuntimeError):
    pass


class CapabilityWorkflowRecord(StrictModel):
    workflow_id: str
    proposal_id: str
    session_id: str
    run_id: str
    requested_capability: str
    tool_name: str
    tool_version: str
    tool_definition_hash: str
    proposal: dict
    original_action: dict
    draft_path: str | None = None
    status: str
    retry_status: str
    created_at: str
    updated_at: str
    expires_at: str
    execution_result: dict | None = None


class CapabilityWorkflowRepository:
    _pending_statuses = {
        "WAITING_TOOL_APPROVAL",
        "WAITING_RETRY_CONFIRMATION",
    }

    def __init__(
        self,
        database_file: Path,
        *,
        max_pending_per_session: int = 3,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._database_file = Path(database_file)
        self._database_file.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self._database_file,
            check_same_thread=False,
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._lock = RLock()
        self._max_pending_per_session = max_pending_per_session
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS capability_workflows (
                    workflow_id TEXT PRIMARY KEY,
                    proposal_id TEXT NOT NULL UNIQUE,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    requested_capability TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_version TEXT NOT NULL,
                    tool_definition_hash TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    original_action_json TEXT NOT NULL,
                    draft_path TEXT,
                    status TEXT NOT NULL,
                    retry_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    execution_result_json TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_capability_workflows_session_status
                ON capability_workflows (session_id, status, created_at)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_capability_workflows_expiry
                ON capability_workflows (expires_at, status)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_capability_workflows_tool_identity
                ON capability_workflows (
                    tool_name,
                    tool_version,
                    tool_definition_hash
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS capability_tool_leases (
                    tool_key TEXT PRIMARY KEY,
                    owner_workflow_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def create(
        self,
        record: CapabilityWorkflowRecord,
    ) -> CapabilityWorkflowRecord:
        with self._lock, self._connection:
            if record.status == "WAITING_TOOL_APPROVAL":
                count = self._connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM capability_workflows
                    WHERE session_id = ?
                      AND status = 'WAITING_TOOL_APPROVAL'
                    """,
                    (record.session_id,),
                ).fetchone()[0]
                if count >= self._max_pending_per_session:
                    raise PendingWorkflowLimit(record.session_id)
            self._connection.execute(
                """
                INSERT INTO capability_workflows (
                    workflow_id,
                    proposal_id,
                    session_id,
                    run_id,
                    requested_capability,
                    tool_name,
                    tool_version,
                    tool_definition_hash,
                    proposal_json,
                    original_action_json,
                    draft_path,
                    status,
                    retry_status,
                    created_at,
                    updated_at,
                    expires_at,
                    execution_result_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._record_values(record),
            )
        return record

    def load(self, workflow_id: str) -> CapabilityWorkflowRecord | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT workflow_id, proposal_id, session_id, run_id,
                       requested_capability, tool_name, tool_version,
                       tool_definition_hash, proposal_json,
                       original_action_json, draft_path, status,
                       retry_status, created_at, updated_at, expires_at,
                       execution_result_json
                FROM capability_workflows
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def find_equivalent_pending(
        self,
        session_id: str,
        tool_name: str,
        version: str,
        definition_hash: str,
    ) -> CapabilityWorkflowRecord | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT workflow_id, proposal_id, session_id, run_id,
                       requested_capability, tool_name, tool_version,
                       tool_definition_hash, proposal_json,
                       original_action_json, draft_path, status,
                       retry_status, created_at, updated_at, expires_at,
                       execution_result_json
                FROM capability_workflows
                WHERE session_id = ?
                  AND tool_name = ?
                  AND tool_version = ?
                  AND tool_definition_hash = ?
                  AND status IN (
                      'WAITING_TOOL_APPROVAL',
                      'WAITING_RETRY_CONFIRMATION'
                  )
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (session_id, tool_name, version, definition_hash),
            ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def list_pending(
        self,
        session_id: str | None = None,
    ) -> list[CapabilityWorkflowRecord]:
        placeholders = ", ".join("?" for _ in self._pending_statuses)
        parameters: list[str] = list(sorted(self._pending_statuses))
        where = f"status IN ({placeholders})"
        if session_id is not None:
            where += " AND session_id = ?"
            parameters.append(session_id)
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT workflow_id, proposal_id, session_id, run_id,
                       requested_capability, tool_name, tool_version,
                       tool_definition_hash, proposal_json,
                       original_action_json, draft_path, status,
                       retry_status, created_at, updated_at, expires_at,
                       execution_result_json
                FROM capability_workflows
                WHERE {where}
                ORDER BY created_at ASC
                """,
                parameters,
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def count_pending_tool_approvals(self, session_id: str) -> int:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT COUNT(*)
                FROM capability_workflows
                WHERE session_id = ?
                  AND status = 'WAITING_TOOL_APPROVAL'
                """,
                (session_id,),
            ).fetchone()
        return int(row[0])

    def transition(
        self,
        workflow_id: str,
        *,
        expected: str,
        target: str,
        **updates,
    ) -> CapabilityWorkflowRecord | None:
        allowed_updates = {
            "draft_path",
            "retry_status",
            "execution_result",
            "expires_at",
        }
        unknown = set(updates).difference(allowed_updates)
        if unknown:
            raise ValueError(
                f"unsupported workflow updates: {', '.join(sorted(unknown))}"
            )
        assignments = ["status = ?", "updated_at = ?"]
        parameters: list[object] = [
            target,
            self._now_fn().isoformat(),
        ]
        for key, value in updates.items():
            column = (
                "execution_result_json"
                if key == "execution_result"
                else key
            )
            assignments.append(f"{column} = ?")
            parameters.append(
                json.dumps(value, ensure_ascii=True)
                if key == "execution_result" and value is not None
                else value
            )
        parameters.extend([workflow_id, expected])
        with self._lock, self._connection:
            cursor = self._connection.execute(
                f"""
                UPDATE capability_workflows
                SET {", ".join(assignments)}
                WHERE workflow_id = ? AND status = ?
                """,
                parameters,
            )
        return self.load(workflow_id) if cursor.rowcount == 1 else None

    def claim_retry(self, workflow_id: str) -> bool:
        return self._update_retry_status(
            workflow_id,
            expected="pending",
            target="executing",
        )

    def complete_retry(
        self,
        workflow_id: str,
        *,
        status: str,
        result: dict,
    ) -> bool:
        if status not in {"executed", "failed"}:
            raise ValueError("retry status must be executed or failed")
        now = self._now_fn().isoformat()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE capability_workflows
                SET retry_status = ?,
                    execution_result_json = ?,
                    updated_at = ?
                WHERE workflow_id = ? AND retry_status = 'executing'
                """,
                (
                    status,
                    json.dumps(result, ensure_ascii=True),
                    now,
                    workflow_id,
                ),
            )
        return cursor.rowcount == 1

    def list_expired(
        self,
        *,
        now: datetime | None = None,
    ) -> list[CapabilityWorkflowRecord]:
        cutoff = (now or self._now_fn()).isoformat()
        placeholders = ", ".join("?" for _ in self._pending_statuses)
        parameters = [cutoff, *sorted(self._pending_statuses)]
        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT workflow_id, proposal_id, session_id, run_id,
                       requested_capability, tool_name, tool_version,
                       tool_definition_hash, proposal_json,
                       original_action_json, draft_path, status,
                       retry_status, created_at, updated_at, expires_at,
                       execution_result_json
                FROM capability_workflows
                WHERE expires_at <= ?
                  AND status IN ({placeholders})
                ORDER BY expires_at ASC
                """,
                parameters,
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def acquire_tool_lease(
        self,
        tool_key: str,
        owner_workflow_id: str,
        *,
        expires_at: datetime,
    ) -> bool:
        now = self._now_fn()
        now_text = now.isoformat()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    SELECT owner_workflow_id, expires_at
                    FROM capability_tool_leases
                    WHERE tool_key = ?
                    """,
                    (tool_key,),
                ).fetchone()
                if row is not None:
                    current_owner, current_expiry = row
                    if (
                        current_owner != owner_workflow_id
                        and datetime.fromisoformat(current_expiry) > now
                    ):
                        self._connection.rollback()
                        return False
                self._connection.execute(
                    """
                    INSERT INTO capability_tool_leases (
                        tool_key,
                        owner_workflow_id,
                        expires_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(tool_key) DO UPDATE SET
                        owner_workflow_id = excluded.owner_workflow_id,
                        expires_at = excluded.expires_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        tool_key,
                        owner_workflow_id,
                        expires_at.isoformat(),
                        now_text,
                    ),
                )
                self._connection.commit()
                return True
            except Exception:
                self._connection.rollback()
                raise

    def release_tool_lease(
        self,
        tool_key: str,
        owner_workflow_id: str,
    ) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                DELETE FROM capability_tool_leases
                WHERE tool_key = ? AND owner_workflow_id = ?
                """,
                (tool_key, owner_workflow_id),
            )
        return cursor.rowcount == 1

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _update_retry_status(
        self,
        workflow_id: str,
        *,
        expected: str,
        target: str,
    ) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE capability_workflows
                SET retry_status = ?, updated_at = ?
                WHERE workflow_id = ? AND retry_status = ?
                """,
                (
                    target,
                    self._now_fn().isoformat(),
                    workflow_id,
                    expected,
                ),
            )
        return cursor.rowcount == 1

    @staticmethod
    def _record_values(record: CapabilityWorkflowRecord) -> tuple:
        return (
            record.workflow_id,
            record.proposal_id,
            record.session_id,
            record.run_id,
            record.requested_capability,
            record.tool_name,
            record.tool_version,
            record.tool_definition_hash,
            json.dumps(record.proposal, ensure_ascii=True),
            json.dumps(record.original_action, ensure_ascii=True),
            record.draft_path,
            record.status,
            record.retry_status,
            record.created_at,
            record.updated_at,
            record.expires_at,
            (
                json.dumps(record.execution_result, ensure_ascii=True)
                if record.execution_result is not None
                else None
            ),
        )

    @staticmethod
    def _record_from_row(row: tuple) -> CapabilityWorkflowRecord:
        return CapabilityWorkflowRecord(
            workflow_id=row[0],
            proposal_id=row[1],
            session_id=row[2],
            run_id=row[3],
            requested_capability=row[4],
            tool_name=row[5],
            tool_version=row[6],
            tool_definition_hash=row[7],
            proposal=json.loads(row[8]),
            original_action=json.loads(row[9]),
            draft_path=row[10],
            status=row[11],
            retry_status=row[12],
            created_at=row[13],
            updated_at=row[14],
            expires_at=row[15],
            execution_result=(
                json.loads(row[16]) if row[16] is not None else None
            ),
        )
