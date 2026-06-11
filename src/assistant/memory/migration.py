from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

from assistant.memory.long_term import LongTermMemoryStore
from assistant.memory.models import (
    MemoryCandidate,
    MemoryDecision,
    MemoryStatus,
    MemoryType,
)
from assistant.memory.policy import MemoryPolicy
from assistant.memory.repository import MemoryRepository


@dataclass(frozen=True)
class MigrationReport:
    imported: int
    skipped: int


class MarkdownMemoryMigrator:
    def __init__(
        self,
        repository: MemoryRepository,
        legacy_store: LongTermMemoryStore,
        policy: MemoryPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._legacy_store = legacy_store
        self._policy = policy or MemoryPolicy()

    def migrate(self) -> MigrationReport:
        imported = 0
        skipped = 0
        for memory in self._legacy_store.list_memories():
            source_ref = self._source_ref(memory)
            if self._repository.find_by_source_ref(source_ref) is not None:
                skipped += 1
                continue
            observed_at = self._parse_date(memory.get("date"))
            candidate = MemoryCandidate(
                type=self._legacy_type(memory.get("context", "")),
                content=memory["learning"],
                scope="user",
                importance=0.5,
                source="legacy_markdown",
                source_ref=source_ref,
                observed_at=observed_at,
            )
            classification = self._policy.decide(candidate)
            if classification.decision is MemoryDecision.BLOCK:
                self._repository.record_event(
                    "memory_block",
                    {
                        "reason": classification.reason,
                        "source": "legacy_markdown",
                    },
                )
                skipped += 1
                continue
            self._repository.create(candidate, MemoryStatus.ACTIVE)
            imported += 1
        return MigrationReport(imported=imported, skipped=skipped)

    @staticmethod
    def _source_ref(memory: dict) -> str:
        stable = "|".join(
            [
                str(memory.get("source_file", "")),
                str(memory.get("date", "")),
                str(memory.get("context", "")),
                str(memory.get("learning", "")),
            ]
        )
        digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()
        return f"markdown:{digest}"

    @staticmethod
    def _parse_date(value: str | None) -> datetime:
        if value:
            try:
                parsed = datetime.fromisoformat(value)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _legacy_type(context: str) -> MemoryType:
        if "prefer" in context.lower():
            return MemoryType.USER_PREFERENCE
        return MemoryType.CORRECTION
