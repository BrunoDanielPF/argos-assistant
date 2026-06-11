from dataclasses import dataclass
from enum import Enum
import ntpath
import posixpath
import re
import unicodedata


HELP_RESPONSE = (
    "Posso:\n"
    "- responder perguntas;\n"
    "- abrir apps e sites;\n"
    "- buscar arquivos;\n"
    "- criar e editar arquivos com confirmação;\n"
    "- gerenciar memória;\n"
    "- executar workflows aprovados;\n"
    "- investigar falhas;\n"
    "- cancelar o fluxo atual com /cancel."
)


class PendingResolutionStatus(str, Enum):
    HELP = "help"
    CANCEL = "cancel"
    RESOLVED = "resolved"
    NEW_INTENT = "new_intent"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class PendingResolution:
    status: PendingResolutionStatus
    value: str | int | None = None
    question: str | None = None


class PendingClarificationResolver:
    _HELP_MARKERS = (
        "/help",
        "help",
        "ajuda",
        "oque voce pode fazer",
        "o que voce pode fazer",
        "como voce pode me ajudar",
        "quais comandos posso usar",
    )
    _CANCEL_MARKERS = (
        "/cancel",
        "cancelar",
        "cancele",
        "esquece",
        "deixa pra la",
    )

    def resolve(
        self,
        user_input: str,
        pending: dict | None = None,
    ) -> PendingResolution:
        normalized = self._normalize(user_input)
        if self._is_help(normalized):
            return PendingResolution(PendingResolutionStatus.HELP)
        if normalized in self._CANCEL_MARKERS:
            return PendingResolution(PendingResolutionStatus.CANCEL)

        if not isinstance(pending, dict):
            return PendingResolution(PendingResolutionStatus.NOT_APPLICABLE)
        if normalized.startswith("esquece ") or normalized.startswith("deixa pra la "):
            return PendingResolution(PendingResolutionStatus.NEW_INTENT)
        if pending.get("field") != "path":
            return PendingResolution(PendingResolutionStatus.NOT_APPLICABLE)

        option_value = self._match_option(user_input, pending)
        if option_value is not None:
            if option_value == "cancel":
                return PendingResolution(PendingResolutionStatus.CANCEL)
            return PendingResolution(
                PendingResolutionStatus.RESOLVED,
                value=option_value,
            )

        value = user_input.strip().strip("\"'")
        if value.isdigit():
            return PendingResolution(
                PendingResolutionStatus.UNRESOLVED,
                question=self._format_question(pending),
            )
        if self._starts_new_intent(normalized):
            return PendingResolution(PendingResolutionStatus.NEW_INTENT)
        if self._is_path(value):
            return PendingResolution(
                PendingResolutionStatus.RESOLVED,
                value=value,
            )
        if self._looks_like_new_intent(normalized):
            return PendingResolution(PendingResolutionStatus.NEW_INTENT)
        return PendingResolution(
            PendingResolutionStatus.UNRESOLVED,
            question=self._format_question(pending),
        )

    def build_action(self, pending: dict, value: str | int) -> dict:
        action = pending.get("action")
        field = pending.get("field")
        if not isinstance(action, dict) or not isinstance(field, str):
            raise ValueError("Invalid pending clarification")
        capability = action.get("capability")
        arguments = action.get("arguments")
        if not isinstance(capability, str) or not isinstance(arguments, dict):
            raise ValueError("Invalid pending clarification action")
        return {
            "mode": "action",
            "capability": capability,
            "arguments": {**arguments, field: value},
        }

    def _is_help(self, normalized: str) -> bool:
        if normalized in {"/help", "help", "ajuda"}:
            return True
        return any(marker in normalized for marker in self._HELP_MARKERS[3:])

    def _match_option(self, user_input: str, pending: dict) -> str | int | None:
        options = [
            option
            for option in pending.get("options", [])
            if isinstance(option, dict)
            and isinstance(option.get("id"), (str, int))
        ]
        number_match = re.fullmatch(r"\s*(\d+)\s*", user_input)
        if number_match:
            index = int(number_match.group(1)) - 1
            if 0 <= index < len(options):
                return options[index]["id"]
            return None

        normalized = self._normalize(user_input)
        for option in options:
            option_id = option["id"]
            label = option.get("label")
            if normalized == self._normalize(str(option_id)):
                return option_id
            if isinstance(label, str) and normalized == self._normalize(label):
                return option_id
        return None

    @staticmethod
    def _is_path(value: str) -> bool:
        if not value or "\n" in value or "\r" in value:
            return False
        if re.match(r"^[a-z][a-z0-9+.-]*://", value, flags=re.IGNORECASE):
            return False
        if ntpath.isabs(value) or posixpath.isabs(value):
            return True
        if value.startswith(("./", "../", ".\\", "..\\")):
            return PendingClarificationResolver._valid_relative_path(value)
        if "/" in value or "\\" in value:
            return PendingClarificationResolver._valid_relative_path(value)
        return bool(
            re.fullmatch(
                r"[^<>:\"/\\|?*\s][^<>:\"/\\|?*]*\.[A-Za-z0-9][A-Za-z0-9._-]*",
                value,
            )
        )

    @staticmethod
    def _valid_relative_path(value: str) -> bool:
        if re.search(r'[<>"|?*]', value):
            return False
        if ":" in value and not re.match(r"^[A-Za-z]:[\\/]", value):
            return False
        return bool(value.strip())

    @staticmethod
    def _looks_like_new_intent(normalized: str) -> bool:
        if "?" in normalized:
            return True
        words = normalized.split()
        if len(words) >= 4:
            return True
        return PendingClarificationResolver._starts_new_intent(normalized)

    @staticmethod
    def _starts_new_intent(normalized: str) -> bool:
        return normalized.startswith(
            (
                "nao quero ",
                "quero ",
                "voce ",
                "como ",
                "porque ",
                "por que ",
                "crie ",
                "abra ",
                "execute ",
            )
        )

    @staticmethod
    def _format_question(pending: dict) -> str:
        lines = [str(pending.get("question", "Preciso de mais detalhes."))]
        for index, option in enumerate(pending.get("options", []), start=1):
            if isinstance(option, dict):
                lines.append(
                    f"{index}. {option.get('label', option.get('id', 'opcao'))}"
                )
        return "\n".join(lines)

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.strip())
        without_accents = "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        )
        normalized = re.sub(r"\s+", " ", without_accents.casefold())
        return normalized.strip(" .,!?")
