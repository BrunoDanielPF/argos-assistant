from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock

from assistant.memory.models import (
    MemoryCandidate,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
)


class MemoryRepository:
    def __init__(self, database_file: Path) -> None:
        self._database_file = Path(database_file)
        self._database_file.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self._database_file,
            check_same_thread=False,
        )
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._lock = RLock()
        self._create_schema()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    scope_value TEXT,
                    importance REAL NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    source_ref TEXT UNIQUE,
                    observed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT,
                    kind TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memories_status_scope
                ON memories(status, scope, scope_value)
                """
            )

    def create(
        self,
        candidate: MemoryCandidate,
        status: MemoryStatus,
    ) -> MemoryRecord:
        record = MemoryRecord(
            type=candidate.type,
            status=status,
            content=candidate.content,
            scope=candidate.scope,
            scope_value=candidate.scope_value,
            importance=candidate.importance,
            confidence=candidate.confidence,
            source=candidate.source,
            source_ref=candidate.source_ref,
            observed_at=candidate.observed_at,
        )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO memories (
                    id, type, status, content, scope, scope_value,
                    importance, confidence, source, source_ref,
                    observed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._record_values(record),
            )
            self._write_event_locked(
                record.id,
                "memory_created",
                {"status": status.value, "type": record.type.value},
            )
        return record

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def find_by_source_ref(self, source_ref: str) -> MemoryRecord | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM memories WHERE source_ref = ?",
                (source_ref,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(
        self,
        status: MemoryStatus | None = None,
    ) -> list[MemoryRecord]:
        query = "SELECT * FROM memories"
        parameters: tuple = ()
        if status is not None:
            query += " WHERE status = ?"
            parameters = (status.value,)
        query += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [self._from_row(row) for row in rows]

    def update_status(
        self,
        memory_id: str,
        status: MemoryStatus,
    ) -> MemoryRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE memories SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, now, memory_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(memory_id)
            self._write_event_locked(
                memory_id,
                "memory_status_changed",
                {"status": status.value},
            )
        record = self.get(memory_id)
        assert record is not None
        return record

    def record_event(
        self,
        kind: str,
        details: dict,
        memory_id: str | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._write_event_locked(memory_id, kind, details)

    def list_events(self, memory_id: str | None = None) -> list[dict]:
        query = (
            "SELECT memory_id, kind, details_json, created_at "
            "FROM memory_events"
        )
        parameters: tuple = ()
        if memory_id is not None:
            query += " WHERE memory_id = ?"
            parameters = (memory_id,)
        query += " ORDER BY event_id"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [
            {
                "memory_id": row[0],
                "kind": row[1],
                "details": json.loads(row[2]),
                "created_at": row[3],
            }
            for row in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _write_event_locked(
        self,
        memory_id: str | None,
        kind: str,
        details: dict,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO memory_events (
                memory_id, kind, details_json, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                memory_id,
                kind,
                json.dumps(details, ensure_ascii=True, sort_keys=True),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    @staticmethod
    def _record_values(record: MemoryRecord) -> tuple:
        return (
            record.id,
            record.type.value,
            record.status.value,
            record.content,
            record.scope,
            record.scope_value,
            record.importance,
            record.confidence,
            record.source,
            record.source_ref,
            record.observed_at.isoformat(),
            record.created_at.isoformat(),
            record.updated_at.isoformat(),
        )

    @staticmethod
    def _from_row(row: tuple) -> MemoryRecord:
        return MemoryRecord(
            id=row[0],
            type=MemoryType(row[1]),
            status=MemoryStatus(row[2]),
            content=row[3],
            scope=row[4],
            scope_value=row[5],
            importance=row[6],
            confidence=row[7],
            source=row[8],
            source_ref=row[9],
            observed_at=datetime.fromisoformat(row[10]),
            created_at=datetime.fromisoformat(row[11]),
            updated_at=datetime.fromisoformat(row[12]),
        )
