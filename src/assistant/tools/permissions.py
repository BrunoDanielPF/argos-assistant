from dataclasses import dataclass
from pathlib import Path
import re

from assistant.tools.models import ToolPermissions


class UnsafeToolPermission(ValueError):
    pass


@dataclass(frozen=True)
class EffectivePermissions:
    filesystem_read: list[str]
    filesystem_write: list[str]
    network_enabled: bool
    network_hosts: list[str]
    subprocess_executables: list[str]


def expand_permissions(
    permissions: ToolPermissions | dict,
    arguments: dict,
) -> EffectivePermissions:
    model = (
        permissions
        if isinstance(permissions, ToolPermissions)
        else ToolPermissions.model_validate(permissions)
    )
    reads = [_expand_pattern(pattern, arguments) for pattern in model.filesystem.read]
    writes = [_expand_pattern(pattern, arguments) for pattern in model.filesystem.write]
    for pattern in writes:
        _validate_write_pattern(pattern)
    return EffectivePermissions(
        filesystem_read=reads,
        filesystem_write=writes,
        network_enabled=model.network.enabled,
        network_hosts=list(model.network.hosts),
        subprocess_executables=list(model.subprocess.executables),
    )


def _expand_pattern(pattern: str, arguments: dict) -> str:
    def replace(match: re.Match) -> str:
        field = match.group(1)
        value = arguments.get(field)
        if not isinstance(value, (str, int)):
            raise UnsafeToolPermission(f"missing permission argument: {field}")
        return str(value)

    expanded = re.sub(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}", replace, pattern)
    if expanded.endswith("/**") or expanded.endswith("\\**"):
        return str(Path(expanded[:-3]) / "**")
    return str(Path(expanded))


def _validate_write_pattern(pattern: str) -> None:
    normalized = pattern.replace("\\", "/").lower().rstrip("/")
    unsafe_suffixes = (
        "/users/*/**",
        "/users/example/**",
        "/.ssh/**",
        "/.gnupg/**",
        "/windows/**",
        "/program files/**",
    )
    if re.fullmatch(r"[a-z]:/\*\*", normalized):
        raise UnsafeToolPermission("disk-wide write permission is not allowed")
    if any(normalized.endswith(suffix) for suffix in unsafe_suffixes):
        raise UnsafeToolPermission("broad or sensitive write permission is not allowed")
    base = normalized.removesuffix("/**")
    if base in {"", ".", "/", str(Path.home()).replace("\\", "/").lower()}:
        raise UnsafeToolPermission("home-wide write permission is not allowed")
