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
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS confirmations (
                    confirmation_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
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

    def save_confirmation(
        self,
        confirmation_id: str,
        session_id: str,
        run_id: str,
        capability: str,
        arguments: dict,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO confirmations (
                    confirmation_id,
                    session_id,
                    run_id,
                    capability,
                    arguments_json,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    confirmation_id,
                    session_id,
                    run_id,
                    capability,
                    json.dumps(arguments, ensure_ascii=True),
                    now,
                ),
            )

    def load_confirmation(self, confirmation_id: str) -> dict | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT confirmation_id, session_id, run_id, capability,
                       arguments_json, status, created_at, resolved_at
                FROM confirmations
                WHERE confirmation_id = ?
                """,
                (confirmation_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "confirmation_id": row[0],
            "session_id": row[1],
            "run_id": row[2],
            "capability": row[3],
            "arguments": json.loads(row[4]),
            "status": row[5],
            "created_at": row[6],
            "resolved_at": row[7],
        }

    def resolve_confirmation(
        self,
        confirmation_id: str,
        approved: bool,
    ) -> dict | None:
        status = "approved" if approved else "rejected"
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE confirmations
                SET status = ?, resolved_at = ?
                WHERE confirmation_id = ? AND status = 'pending'
                """,
                (status, now, confirmation_id),
            )
        if cursor.rowcount != 1:
            return None
        return self.load_confirmation(confirmation_id)

    def close(self) -> None:
        with self._lock:
            self._connection.close()
