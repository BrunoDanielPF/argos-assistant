import json
from pathlib import Path
from threading import Lock

from assistant.recovery.classifier import redact_sensitive
from assistant.recovery.models import RecoveryAttempt, RecoveryOutcome


class RecoveryRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = Lock()

    def write(self, outcome: RecoveryOutcome) -> None:
        payload = {
            "record_type": "recovery_outcome",
            **redact_sensitive(outcome.model_dump(mode="json")),
        }
        self._append(payload)

    def write_attempt(self, attempt: RecoveryAttempt) -> None:
        self._append(
            {
                "record_type": "recovery_attempt",
                "attempt": redact_sensitive(
                    attempt.model_dump(mode="json")
                ),
            }
        )

    def _append(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n"
            )
