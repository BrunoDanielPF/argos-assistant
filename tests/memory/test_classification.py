from assistant.memory.classifier import MemoryClassifier
from assistant.memory.extractor import MemoryExtractor
from assistant.memory.models import (
    MemoryDecision,
    MemoryStatus,
    MemoryType,
)
from assistant.memory.policy import MemoryPolicy


def test_project_decision_requires_confirmation_with_project_scope():
    extractor = MemoryExtractor()
    classifier = MemoryClassifier(MemoryPolicy(allow_auto_save_low_risk=True))

    candidates = extractor.extract(
        "não quero usar LangChain no core do Argos por enquanto",
        assistant_response="Entendido.",
        context={"current_cwd": "C:\\workspace\\argos"},
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.type is MemoryType.PROJECT_DECISION
    assert candidate.scope == "project"
    assert candidate.scope_value == "C:\\workspace\\argos"

    classification = classifier.classify(candidate)
    assert classification.decision is MemoryDecision.CONFIRM
    assert classification.status is MemoryStatus.PENDING


def test_sensitive_candidate_is_blocked():
    extractor = MemoryExtractor()
    classifier = MemoryClassifier(MemoryPolicy())

    candidate = extractor.extract(
        "lembre que meu token é abc123",
        assistant_response="",
        context={},
    )[0]
    classification = classifier.classify(candidate)

    assert classification.decision is MemoryDecision.BLOCK
    assert classification.status is None


def test_low_risk_memory_only_auto_saves_when_enabled():
    candidate = MemoryExtractor().extract(
        "lembre que prefiro respostas curtas",
        assistant_response="",
        context={},
    )[0]

    disabled = MemoryClassifier(
        MemoryPolicy(allow_auto_save_low_risk=False)
    ).classify(candidate)
    enabled = MemoryClassifier(
        MemoryPolicy(allow_auto_save_low_risk=True)
    ).classify(candidate)

    assert disabled.decision is MemoryDecision.CONFIRM
    assert disabled.status is MemoryStatus.PENDING
    assert enabled.decision is MemoryDecision.AUTO_SAVE
    assert enabled.status is MemoryStatus.ACTIVE

