from pathlib import Path

import yaml

from assistant.tools.models import ToolManifest


class ToolManifestError(ValueError):
    pass


def load_tool_manifest(tool_dir: Path) -> ToolManifest:
    tool_dir = Path(tool_dir).resolve()
    manifest_path = tool_dir / "tool.yaml"
    try:
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest = ToolManifest.model_validate(payload)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise ToolManifestError(str(exc)) from exc

    entrypoint = (tool_dir / manifest.runtime.entrypoint).resolve()
    try:
        entrypoint.relative_to(tool_dir)
    except ValueError as exc:
        raise ToolManifestError("runtime entrypoint escapes tool directory") from exc
    if not entrypoint.is_file():
        raise ToolManifestError("runtime entrypoint does not exist")
    return manifest
