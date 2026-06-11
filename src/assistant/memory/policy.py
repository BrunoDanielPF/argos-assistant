import unicodedata

from assistant.memory.models import (
    MemoryCandidate,
    MemoryClassification,
    MemoryDecision,
    MemoryStatus,
    MemoryType,
)


class MemoryPolicy:
    _sensitive_patterns = (
        "senha",
        "password",
        "token",
        "api key",
        "apikey",
        "secret",
        "chave privada",
        "private key",
        "credential",
    )
    _important_types = {MemoryType.PROJECT_DECISION}

    def __init__(self, allow_auto_save_low_risk: bool = False) -> None:
        self.allow_auto_save_low_risk = allow_auto_save_low_risk

    def decide(self, candidate: MemoryCandidate) -> MemoryClassification:
        normalized = self._normalize(candidate.content)
        if any(pattern in normalized for pattern in self._sensitive_patterns):
            return MemoryClassification(
                decision=MemoryDecision.BLOCK,
                reason="sensitive_content",
            )
        if candidate.type in self._important_types:
            return MemoryClassification(
                decision=MemoryDecision.CONFIRM,
                status=MemoryStatus.PENDING,
                reason="important_memory_requires_confirmation",
            )
        if self.allow_auto_save_low_risk:
            return MemoryClassification(
                decision=MemoryDecision.AUTO_SAVE,
                status=MemoryStatus.ACTIVE,
                reason="low_risk_auto_save_enabled",
            )
        return MemoryClassification(
            decision=MemoryDecision.CONFIRM,
            status=MemoryStatus.PENDING,
            reason="auto_save_disabled",
        )

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        return "".join(
            char for char in decomposed if not unicodedata.combining(char)
        ).lower()

