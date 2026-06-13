from __future__ import annotations

from assistant.capabilities.registry import build_default_registry


class CapabilityArgumentResolver:
    _context_fields = {
        "root": ("current_cwd", "default_search_root"),
        "source_root": ("current_cwd", "default_search_root"),
        "cwd": ("current_cwd", "default_search_root"),
    }

    def __init__(self, registry=None) -> None:
        self._registry = registry or build_default_registry()

    def resolve(
        self,
        capability_name: str,
        arguments: dict,
        context: dict,
    ) -> dict:
        resolved = dict(arguments)
        allowed_fields = self._schema_fields(capability_name)
        for field, context_keys in self._context_fields.items():
            if field in resolved:
                continue
            if allowed_fields is not None and field not in allowed_fields:
                continue
            for context_key in context_keys:
                value = context.get(context_key)
                if isinstance(value, str) and value.strip():
                    resolved[field] = value
                    break
        return resolved

    def _schema_fields(self, capability_name: str) -> set[str]:
        capability = self._registry.resolve(capability_name)
        if capability is None:
            return set()
        return set(capability.schema.model_fields)
