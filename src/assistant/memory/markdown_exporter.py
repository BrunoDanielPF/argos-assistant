from pathlib import Path

from assistant.memory.repository import MemoryRepository


class MarkdownMemoryExporter:
    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

    def export(self, target: Path) -> Path:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Argos Memory Export", ""]
        for memory in self._repository.list():
            lines.extend(
                [
                    f"## {memory.type.value}: {memory.id}",
                    "",
                    f"- Status: {memory.status.value}",
                    f"- Scope: {memory.scope}",
                    f"- Scope value: {memory.scope_value or '-'}",
                    f"- Importance: {memory.importance:.2f}",
                    f"- Observed at: {memory.observed_at.isoformat()}",
                    f"- Source: {memory.source}",
                    f"- Memory: {memory.content}",
                    "",
                ]
            )
        target.write_text("\n".join(lines), encoding="utf-8")
        self._repository.record_event(
            "memory_exported",
            {"target": str(target), "count": len(self._repository.list())},
        )
        return target

