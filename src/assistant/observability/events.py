from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SENSITIVE_KEYS = {"prompt", "content", "token", "secret", "password"}


class SensitiveEventData(ValueError):
    pass


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).lower() in SENSITIVE_KEYS or _contains_sensitive_key(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


class EventLog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def write(
        self,
        kind: str,
        session_id: str,
        run_id: str,
        details: dict | None = None,
    ) -> None:
        event_details = details or {}
        if _contains_sensitive_key(event_details):
            raise SensitiveEventData("event details contain sensitive keys")

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "session_id": session_id,
            "run_id": run_id,
            "details": event_details,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=True) + "\n")
