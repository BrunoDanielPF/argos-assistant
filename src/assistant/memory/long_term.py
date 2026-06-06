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

    def list_memories(self) -> list[dict]:
        if not self._memory_dir.exists():
            return []

        memories = []
        for memory_file in sorted(self._memory_dir.glob("*.md")):
            memories.extend(self._read_memory_file(memory_file))
        return memories

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        query_terms = self._terms(query)
        scored = []
        for memory in self.list_memories():
            haystack = " ".join(
                [
                    memory.get("title", ""),
                    memory.get("context", ""),
                    memory.get("learning", ""),
                ]
            )
            score = len(query_terms.intersection(self._terms(haystack)))
            if score > 0:
                scored.append((score, memory))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in scored[:max_results]]

    def _title_from_learning(self, learning: str) -> str:
        title = learning.strip().rstrip(".")
        title = re.sub(r"\s+", " ", title)
        return title[:80] or "Aprendizado"

    def _read_memory_file(self, memory_file: Path) -> list[dict]:
        content = memory_file.read_text(encoding="utf-8")
        entries = []
        for block in re.split(r"\n(?=## )", content):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines or not lines[0].startswith("## "):
                continue

            entry = {
                "title": lines[0].removeprefix("## ").strip(),
                "source_file": memory_file.name,
            }
            for line in lines[1:]:
                if line.startswith("- Data:"):
                    entry["date"] = line.removeprefix("- Data:").strip()
                elif line.startswith("- Contexto:"):
                    entry["context"] = line.removeprefix("- Contexto:").strip()
                elif line.startswith("- Aprendizado:"):
                    entry["learning"] = line.removeprefix("- Aprendizado:").strip()
                elif line.startswith("- Fonte:"):
                    entry["source"] = line.removeprefix("- Fonte:").strip()

            if entry.get("learning"):
                entries.append(entry)
        return entries

    def _terms(self, text: str) -> set[str]:
        stopwords = {
            "a",
            "as",
            "como",
            "de",
            "devo",
            "do",
            "e",
            "em",
            "eu",
            "o",
            "os",
            "para",
            "que",
            "um",
            "uma",
        }
        return {
            term
            for term in re.findall(r"[a-zA-Z0-9_À-ÿ:]+", text.lower())
            if len(term) > 2 and term not in stopwords
        }
