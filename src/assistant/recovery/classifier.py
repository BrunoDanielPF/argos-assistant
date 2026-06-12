import re
from typing import Any

from assistant.recovery.models import FailureEvent, FailureType


REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "password",
    "private_key",
    "secret",
    "secrets",
    "token",
    "tokens",
}


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if _is_sensitive_key(key)
                else redact_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    return value


def _is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    normalized = re.sub(r"[^a-z0-9_]", "", key.casefold())
    return normalized in _SENSITIVE_KEYS


class FailureClassifier:
    _CODE_MAP = {
        "unsupported_capability": FailureType.UNSUPPORTED_CAPABILITY,
        "capability_gap": FailureType.CAPABILITY_GAP,
        "invalid_schema": FailureType.INVALID_SCHEMA,
        "wrong_intent": FailureType.WRONG_INTENT,
        "no_results": FailureType.NO_RESULTS,
        "execution_failed": FailureType.EXECUTION_FAILED,
        "timeout": FailureType.TIMEOUT,
        "invalid_arguments": FailureType.INVALID_ARGUMENTS,
        "permission_denied": FailureType.PERMISSION_DENIED,
        "policy_blocked": FailureType.POLICY_BLOCKED,
        "context_ambiguity": FailureType.CONTEXT_AMBIGUITY,
    }

    def classify(
        self,
        *,
        source: str,
        operation: str,
        message: str,
        error_code: str | None = None,
        exception: Exception | None = None,
        metadata: dict | None = None,
        attempt: int = 0,
    ) -> FailureEvent:
        failure_type = self._classify_type(
            message=message,
            error_code=error_code,
            exception=exception,
            source=source,
        )
        return FailureEvent(
            source=source,
            operation=operation,
            failure_type=failure_type,
            message=self._safe_message(message),
            error_code=error_code,
            exception_type=type(exception).__name__ if exception else None,
            metadata=redact_sensitive(metadata or {}),
            attempt=attempt,
        )

    def _classify_type(
        self,
        *,
        message: str,
        error_code: str | None,
        exception: Exception | None,
        source: str,
    ) -> FailureType:
        normalized_code = (error_code or "").strip().lower()
        if normalized_code in self._CODE_MAP:
            return self._CODE_MAP[normalized_code]
        if normalized_code:
            return FailureType.EXECUTION_FAILED

        normalized = message.casefold()
        exception_name = type(exception).__name__.casefold() if exception else ""
        if "timeout" in normalized or "timed out" in normalized or "timeout" in exception_name:
            return FailureType.TIMEOUT
        if "blocked capability" in normalized or "policy_blocked" in normalized:
            return FailureType.POLICY_BLOCKED
        if "unsupported capability" in normalized:
            return FailureType.UNSUPPORTED_CAPABILITY
        if "no files matched" in normalized or "no results" in normalized:
            return FailureType.NO_RESULTS
        if "permission" in normalized or "access denied" in normalized:
            return FailureType.PERMISSION_DENIED
        if "invalid argument" in normalized or "missing " in normalized:
            return FailureType.INVALID_SCHEMA
        if "ambiguous" in normalized or "mais de um arquivo" in normalized:
            return FailureType.CONTEXT_AMBIGUITY
        if source == "tool":
            return FailureType.EXECUTION_FAILED
        return FailureType.UNKNOWN

    @staticmethod
    def _safe_message(message: str) -> str:
        message = re.sub(
            r"(?i)\b(token|secret|password|api[_-]?key|credential)"
            r"\s*[:=]\s*[^\s,;]+",
            lambda match: f"{match.group(1)}={REDACTED}",
            message,
        )
        message = re.sub(
            r"(?i)\bbearer\s+[a-z0-9._~+/=-]+",
            f"Bearer {REDACTED}",
            message,
        )
        if len(message) <= 2000:
            return message
        return message[:1997] + "..."
