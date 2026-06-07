from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import Lock
from uuid import uuid4

from assistant.jobs.models import (
    JobRecord,
    JobStatus,
    ensure_valid_transition,
)


class JobRepository:
    def __init__(self, database_file: Path) -> None:
        self._database_file = database_file
        self._database_file.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self._database_file,
            check_same_thread=False,
        )
        self._lock = Lock()
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    scheduled_for TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    last_error TEXT
                )
                """
            )
            existing_columns = {
                row[1]
                for row in self._connection.execute("PRAGMA table_info(jobs)").fetchall()
            }
            if "scheduled_for" not in existing_columns:
                self._connection.execute(
                    "ALTER TABLE jobs ADD COLUMN scheduled_for TEXT"
                )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_updated_at
                ON jobs (updated_at DESC)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_status_schedule
                ON jobs (status, scheduled_for, created_at)
                """
            )

    def create(
        self,
        session_id: str,
        run_id: str,
        payload: dict,
        scheduled_for: datetime | None = None,
    ) -> JobRecord:
        now = datetime.now(timezone.utc)
        job_id = str(uuid4())
        record = JobRecord(
            job_id=job_id,
            session_id=session_id,
            run_id=run_id,
            status=JobStatus.QUEUED,
            payload=dict(payload),
            scheduled_for=scheduled_for,
            created_at=now,
            updated_at=now,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO jobs (
                    job_id,
                    session_id,
                    run_id,
                    status,
                    payload_json,
                    scheduled_for,
                    created_at,
                    updated_at,
                    attempts,
                    last_error
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._serialize(record),
            )
        return record

    def load(self, job_id: str) -> JobRecord | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT job_id, session_id, run_id, status, payload_json, scheduled_for,
                       created_at, updated_at, attempts, last_error
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return self._deserialize(row)

    def list_recent(self, limit: int = 20) -> list[JobRecord]:
        if limit <= 0:
            limit = 20
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT job_id, session_id, run_id, status, payload_json, scheduled_for,
                       created_at, updated_at, attempts, last_error
                FROM jobs
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._deserialize(row) for row in rows]

    def next_queued(self, now: datetime | None = None) -> JobRecord | None:
        now = now or datetime.now(timezone.utc)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT job_id, session_id, run_id, status, payload_json, scheduled_for,
                       created_at, updated_at, attempts, last_error
                FROM jobs
                WHERE status = ?
                  AND (scheduled_for IS NULL OR scheduled_for <= ?)
                ORDER BY COALESCE(scheduled_for, created_at) ASC, created_at ASC
                LIMIT 1
                """,
                (JobStatus.QUEUED.value, now.isoformat()),
            ).fetchone()
        if row is None:
            return None
        return self._deserialize(row)

    def transition(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
    ) -> JobRecord:
        with self._lock, self._connection:
            row = self._connection.execute(
                """
                SELECT job_id, session_id, run_id, status, payload_json, scheduled_for,
                       created_at, updated_at, attempts, last_error
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            current = self._deserialize(row)
            ensure_valid_transition(current.status, status)
            updated_at = datetime.now(timezone.utc)
            attempts = current.attempts + 1 if status == JobStatus.RUNNING else current.attempts
            last_error = error if status == JobStatus.FAILED else None
            self._connection.execute(
                """
                UPDATE jobs
                SET status = ?, updated_at = ?, attempts = ?, last_error = ?
                WHERE job_id = ?
                """,
                (
                    status.value,
                    updated_at.isoformat(),
                    attempts,
                    last_error,
                    job_id,
                ),
            )
        updated = self.load(job_id)
        assert updated is not None
        return updated

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @staticmethod
    def _serialize(record: JobRecord) -> tuple:
        return (
            record.job_id,
            record.session_id,
            record.run_id,
            record.status.value,
            json.dumps(record.payload, ensure_ascii=True),
            record.scheduled_for.isoformat() if record.scheduled_for else None,
            record.created_at.isoformat(),
            record.updated_at.isoformat(),
            record.attempts,
            record.last_error,
        )

    @staticmethod
    def _deserialize(row) -> JobRecord:
        return JobRecord(
            job_id=row[0],
            session_id=row[1],
            run_id=row[2],
            status=JobStatus(row[3]),
            payload=json.loads(row[4]),
            scheduled_for=datetime.fromisoformat(row[5]) if row[5] else None,
            created_at=datetime.fromisoformat(row[6]),
            updated_at=datetime.fromisoformat(row[7]),
            attempts=int(row[8]),
            last_error=row[9],
        )
