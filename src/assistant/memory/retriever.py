from datetime import datetime, timezone
import math
import re
import unicodedata
from typing import Protocol

from assistant.memory.models import MemoryRecord, MemoryStatus
from assistant.memory.repository import MemoryRepository


class MemoryRetriever(Protocol):
    def retrieve(
        self,
        query: str,
        context: dict,
        limit: int = 5,
    ) -> list[MemoryRecord]: ...


class LexicalMemoryRetriever:
    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

    def retrieve(
        self,
        query: str,
        context: dict,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        query_terms = self._terms(query)
        if not query_terms:
            return []
        scored = []
        for memory in self._repository.list(status=MemoryStatus.ACTIVE):
            if not self._scope_matches(memory, context):
                continue
            overlap = len(query_terms.intersection(self._terms(memory.content)))
            if overlap == 0:
                continue
            age_days = max(
                0.0,
                (datetime.now(timezone.utc) - memory.observed_at).total_seconds()
                / 86400,
            )
            recency = 1.0 / (1.0 + math.log1p(age_days))
            score = overlap + memory.importance + (0.25 * recency)
            scored.append((score, memory))
        scored.sort(
            key=lambda item: (item[0], item[1].observed_at),
            reverse=True,
        )
        results = [memory for _, memory in scored[:limit]]
        for memory in results:
            self._repository.record_event(
                "memory_retrieved",
                {"query_terms": len(query_terms)},
                memory.id,
            )
        return results

    @staticmethod
    def _scope_matches(memory: MemoryRecord, context: dict) -> bool:
        if memory.scope in {"global", "user"}:
            return True
        current_scope = (
            context.get("project_root")
            or context.get("repo")
            or context.get("current_cwd")
        )
        return bool(
            current_scope
            and memory.scope_value
            and str(current_scope).casefold() == memory.scope_value.casefold()
        )

    @classmethod
    def _terms(cls, value: str) -> set[str]:
        normalized = unicodedata.normalize("NFKD", value)
        normalized = "".join(
            char for char in normalized if not unicodedata.combining(char)
        ).lower()
        stopwords = {
            "a",
            "as",
            "como",
            "de",
            "do",
            "e",
            "em",
            "o",
            "os",
            "para",
            "que",
            "um",
            "uma",
        }
        return {
            term
            for term in re.findall(r"[a-z0-9_:+.-]+", normalized)
            if len(term) > 2 and term not in stopwords
        }

