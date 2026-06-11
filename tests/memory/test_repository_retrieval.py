from datetime import datetime, timedelta, timezone

from assistant.memory.models import (
    MemoryCandidate,
    MemoryStatus,
    MemoryType,
)
from assistant.memory.repository import MemoryRepository
from assistant.memory.retriever import LexicalMemoryRetriever


def test_repository_persists_structured_memory_and_events(tmp_path):
    repository = MemoryRepository(tmp_path / "argos.db")
    candidate = MemoryCandidate(
        type=MemoryType.USER_PREFERENCE,
        content="Prefiro respostas objetivas em portugues.",
        scope="user",
        importance=0.7,
    )

    record = repository.create(candidate, MemoryStatus.ACTIVE)
    loaded = repository.get(record.id)

    assert loaded == record
    assert repository.list_events(record.id)[0]["kind"] == "memory_created"
    repository.close()


def test_lexical_retrieval_filters_scope_and_ranks_importance_and_recency(tmp_path):
    repository = MemoryRepository(tmp_path / "argos.db")
    old = datetime.now(timezone.utc) - timedelta(days=30)
    repository.create(
        MemoryCandidate(
            type=MemoryType.PROJECT_FACT,
            content="O projeto Argos usa Python.",
            scope="project",
            scope_value="C:\\workspace\\argos",
            importance=0.4,
            observed_at=old,
        ),
        MemoryStatus.ACTIVE,
    )
    preferred = repository.create(
        MemoryCandidate(
            type=MemoryType.PROJECT_DECISION,
            content="O core do Argos usa Python sem LangChain.",
            scope="project",
            scope_value="C:\\workspace\\argos",
            importance=0.9,
        ),
        MemoryStatus.ACTIVE,
    )
    repository.create(
        MemoryCandidate(
            type=MemoryType.PROJECT_FACT,
            content="Outro projeto usa Python.",
            scope="project",
            scope_value="C:\\workspace\\other",
            importance=1.0,
        ),
        MemoryStatus.ACTIVE,
    )

    results = LexicalMemoryRetriever(repository).retrieve(
        "qual tecnologia o core do Argos usa?",
        {"current_cwd": "C:\\workspace\\argos"},
        limit=5,
    )

    assert results[0].id == preferred.id
    assert all(item.scope_value != "C:\\workspace\\other" for item in results)
    repository.close()

