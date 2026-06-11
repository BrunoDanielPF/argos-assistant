from assistant.memory.models import MemoryCandidate, MemoryClassification
from assistant.memory.policy import MemoryPolicy


class MemoryClassifier:
    def __init__(self, policy: MemoryPolicy | None = None) -> None:
        self._policy = policy or MemoryPolicy()

    def classify(self, candidate: MemoryCandidate) -> MemoryClassification:
        return self._policy.decide(candidate)

