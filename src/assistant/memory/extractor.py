import re
import unicodedata

from assistant.memory.models import MemoryCandidate, MemoryType


class MemoryExtractor:
    def extract(
        self,
        user_input: str,
        assistant_response: str,
        context: dict,
    ) -> list[MemoryCandidate]:
        del assistant_response
        content = user_input.strip()
        if not content:
            return []

        normalized = self._normalize(content)
        project_scope = (
            context.get("project_root")
            or context.get("repo")
            or context.get("current_cwd")
        )

        if self._is_project_decision(normalized):
            return [
                MemoryCandidate(
                    type=MemoryType.PROJECT_DECISION,
                    content=content,
                    scope="project" if project_scope else "user",
                    scope_value=str(project_scope) if project_scope else None,
                    importance=0.9,
                )
            ]

        explicit = re.match(
            r"^(?:lembre que|aprenda que|remember that)\s+(.+)$",
            content,
            flags=re.IGNORECASE,
        )
        if explicit:
            learning = explicit.group(1).strip()
            memory_type = (
                MemoryType.PROJECT_PREFERENCE
                if project_scope and "projeto" in normalized
                else MemoryType.USER_PREFERENCE
            )
            return [
                MemoryCandidate(
                    type=memory_type,
                    content=learning,
                    scope="project" if memory_type is MemoryType.PROJECT_PREFERENCE else "user",
                    scope_value=(
                        str(project_scope)
                        if memory_type is MemoryType.PROJECT_PREFERENCE
                        else None
                    ),
                    importance=0.6,
                )
            ]

        correction = re.match(
            r"^(?:corrigindo|correcao|correção)\s*:\s*(.+)$",
            content,
            flags=re.IGNORECASE,
        )
        if correction:
            return [
                MemoryCandidate(
                    type=MemoryType.CORRECTION,
                    content=correction.group(1).strip(),
                    scope="project" if project_scope else "user",
                    scope_value=str(project_scope) if project_scope else None,
                    importance=0.8,
                )
            ]
        return []

    @staticmethod
    def _is_project_decision(normalized: str) -> bool:
        decision_markers = (
            "nao quero usar ",
            "nao vamos usar ",
            "decidimos ",
            "fica decidido ",
            "por enquanto nao ",
        )
        project_markers = (
            "core",
            "projeto",
            "repositorio",
            "repo",
            "argos",
            "stack",
        )
        return any(marker in normalized for marker in decision_markers) and any(
            marker in normalized for marker in project_markers
        )

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        return "".join(
            char for char in decomposed if not unicodedata.combining(char)
        ).lower()

