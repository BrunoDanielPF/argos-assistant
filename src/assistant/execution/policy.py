from pathlib import Path

from assistant.capabilities.registry import (
    CapabilityRegistry,
    build_default_registry,
)


def decide_policy(
    capability_name: str,
    arguments: dict | None = None,
    context: dict | None = None,
    *,
    registry: CapabilityRegistry | None = None,
) -> str:
    registry = registry or build_default_registry()
    capability = registry.resolve(capability_name)
    if capability is None:
        return "blocked"

    arguments = arguments or {}
    context = context or {}
    if capability.name == "file.delete_one":
        if arguments.get("recursive") is True:
            return "blocked"
        path = arguments.get("path")
        current_cwd = context.get("current_cwd")
        if isinstance(path, str):
            target = Path(path)
            if target.exists() and target.is_dir():
                return "blocked"
            if isinstance(current_cwd, str):
                try:
                    if target.resolve() == Path(current_cwd).resolve():
                        return "blocked"
                except OSError:
                    return "blocked"
    return capability.policy
