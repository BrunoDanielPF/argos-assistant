from assistant.memory.classifier import MemoryClassifier
from assistant.memory.extractor import MemoryExtractor
from assistant.memory.models import (
    MemoryDecision,
    MemoryObservation,
    MemoryRecord,
)
from assistant.memory.repository import MemoryRepository
from assistant.memory.retriever import LexicalMemoryRetriever, MemoryRetriever


class MemoryEngine:
    def __init__(
        self,
        repository: MemoryRepository,
        extractor: MemoryExtractor | None = None,
        classifier: MemoryClassifier | None = None,
        retriever: MemoryRetriever | None = None,
    ) -> None:
        self._repository = repository
        self._extractor = extractor or MemoryExtractor()
        self._classifier = classifier or MemoryClassifier()
        self._retriever = retriever or LexicalMemoryRetriever(repository)

    def retrieve(self, query: str, context: dict) -> list[MemoryRecord]:
        return self._retriever.retrieve(query, context, limit=5)

    def observe(
        self,
        user_input: str,
        assistant_response: str,
        context: dict,
    ) -> list[MemoryObservation]:
        observations = []
        candidates = self._extractor.extract(
            user_input,
            assistant_response,
            context,
        )
        for candidate in candidates:
            classification = self._classifier.classify(candidate)
            record = None
            if classification.decision in {
                MemoryDecision.AUTO_SAVE,
                MemoryDecision.CONFIRM,
            }:
                assert classification.status is not None
                record = self._repository.create(
                    candidate,
                    classification.status,
                )
            else:
                self._repository.record_event(
                    f"memory_{classification.decision.value}",
                    {
                        "reason": classification.reason,
                        "type": candidate.type.value,
                    },
                )
            observations.append(
                MemoryObservation(
                    candidate=candidate,
                    decision=classification.decision,
                    reason=classification.reason,
                    record=record,
                )
            )
        return observations

