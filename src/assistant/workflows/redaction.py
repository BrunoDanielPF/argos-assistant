import re
from typing import Any


REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = {
    "secret",
    "secrets",
    "token",
    "tokens",
    "password",
    "passwords",
    "apikey",
    "apikeys",
    "privatekey",
    "privatekeys",
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
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return normalized in _SENSITIVE_KEYS
