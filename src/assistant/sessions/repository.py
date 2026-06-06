from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock

from assistant.models import SessionSnapshot


class SessionRepository:
    def __init__(self, database_file: Path) -> None:
        self._database_file = database_file
        self._database_file.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self._database_file,
            check_same_thread=False,
        )
        self._lock = RLock()
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    snapshot_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def save(self, session_id: str, snapshot: dict) -> None:
        validated = SessionSnapshot.model_validate(snapshot)
        serialized = validated.model_dump_json()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO sessions (
                    session_id,
                    snapshot_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    snapshot_json = excluded.snapshot_json,
                    updated_at = excluded.updated_at
                """,
                (session_id, serialized, now, now),
            )

    def load(self, session_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT snapshot_json FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def list_sessions(self) -> list[dict]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT session_id, created_at, updated_at
                FROM sessions
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [
            {
                "session_id": row[0],
                "created_at": row[1],
                "updated_at": row[2],
            }
            for row in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._connection.close()
