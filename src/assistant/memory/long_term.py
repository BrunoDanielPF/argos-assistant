from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re


@dataclass(frozen=True)
class LearningValidation:
    ok: bool
    reason: str = ""


class LongTermMemoryStore:
    _sensitive_patterns = (
        "senha",
        "password",
        "token",
        "api key",
        "apikey",
        "secret",
        "chave privada",
        "private key",
    )

    def __init__(self, memory_dir: Path) -> None:
        self._memory_dir = Path(memory_dir)

    @property
    def memory_dir(self) -> Path:
        return self._memory_dir

    def validate_learning(self, learning: str) -> LearningValidation:
        normalized = learning.strip().lower()
        if not normalized:
            return LearningValidation(ok=False, reason="aprendizado vazio")
        if any(pattern in normalized for pattern in self._sensitive_patterns):
            return LearningValidation(ok=False, reason="conteudo sensivel nao deve ser salvo")
        return LearningValidation(ok=True)

    def remember(
        self,
        learning: str,
        context: str = "geral",
        source: str = "correcao do usuario",
        today: date | None = None,
        topic_file: str = "correcoes.md",
    ) -> Path:
        validation = self.validate_learning(learning)
        if not validation.ok:
            raise ValueError(validation.reason)

        current_date = today or date.today()
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        target = self._memory_dir / topic_file
        is_new_file = not target.exists()

        with target.open("a", encoding="utf-8") as file:
            if is_new_file:
                file.write("# Correcoes\n\n")
            file.write(
                f"## {self._title_from_learning(learning)}\n\n"
                f"- Data: {current_date.isoformat()}\n"
                f"- Contexto: {context}\n"
                f"- Aprendizado: {learning.strip()}\n"
                f"- Fonte: {source}\n\n"
            )
        return target

    def _title_from_learning(self, learning: str) -> str:
        title = learning.strip().rstrip(".")
        title = re.sub(r"\s+", " ", title)
        return title[:80] or "Aprendizado"
