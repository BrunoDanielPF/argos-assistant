from assistant.memory.engine import MemoryEngine
from assistant.memory.models import MemoryDecision, MemoryStatus, MemoryType
from assistant.memory.repository import MemoryRepository


def test_engine_observes_project_decision_as_pending(tmp_path):
    repository = MemoryRepository(tmp_path / "argos.db")
    engine = MemoryEngine(repository)

    observations = engine.observe(
        "não quero usar LangChain no core do Argos por enquanto",
        "Entendido.",
        {"current_cwd": "C:\\workspace\\argos"},
    )

    assert len(observations) == 1
    assert observations[0].decision is MemoryDecision.CONFIRM
    assert observations[0].record is not None
    assert observations[0].record.type is MemoryType.PROJECT_DECISION
    assert observations[0].record.status is MemoryStatus.PENDING
    assert observations[0].record.scope_value == "C:\\workspace\\argos"


def test_engine_does_not_persist_blocked_secret(tmp_path):
    repository = MemoryRepository(tmp_path / "argos.db")
    engine = MemoryEngine(repository)

    observations = engine.observe(
        "lembre que meu token é abc123",
        "Nao vou salvar segredos.",
        {},
    )

    assert observations[0].decision is MemoryDecision.BLOCK
    assert observations[0].record is None
    assert repository.list() == []

