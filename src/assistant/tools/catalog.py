from dataclasses import dataclass
from pathlib import Path

from assistant.tools.manifest import ToolManifestError, load_tool_manifest
from assistant.tools.models import ToolManifest
from assistant.tools.state import ToolStateStore, hash_tool_files


@dataclass(frozen=True)
class CatalogTool:
    manifest: ToolManifest
    path: Path
    trusted: bool = False
    python_executable: str | None = None


class ToolCatalog:
    def __init__(
        self,
        tools_root: Path,
        state_store: ToolStateStore,
        bundled_root: Path | None = None,
        envs_root: Path | None = None,
    ) -> None:
        self._tools_root = Path(tools_root)
        self._state_store = state_store
        self._bundled_root = Path(bundled_root) if bundled_root is not None else None
        self._envs_root = Path(envs_root) if envs_root is not None else None

    def list_enabled(self) -> list[CatalogTool]:
        tools = []
        if self._bundled_root is not None and self._bundled_root.exists():
            for manifest_path in sorted(self._bundled_root.glob("*/tool.yaml")):
                try:
                    manifest = load_tool_manifest(manifest_path.parent)
                except ToolManifestError:
                    continue
                tools.append(
                    CatalogTool(
                        manifest=manifest,
                        path=manifest_path.parent,
                        trusted=True,
                    )
                )
        if not self._tools_root.exists():
            return tools
        for manifest_path in sorted(self._tools_root.glob("*/*/tool.yaml")):
            tool_dir = manifest_path.parent
            try:
                manifest = load_tool_manifest(tool_dir)
            except ToolManifestError:
                continue
            record = self._state_store.get(manifest.name, manifest.version)
            if record is None or record.state != "enabled":
                continue
            record = self._state_store.verify_integrity(
                manifest.name,
                manifest.version,
                hash_tool_files(tool_dir),
            )
            if record.state == "enabled":
                python_executable = None
                if self._envs_root is not None:
                    env_dir = self._envs_root / f"{manifest.name}-{manifest.version}"
                    windows_python = env_dir / "Scripts" / "python.exe"
                    posix_python = env_dir / "bin" / "python"
                    candidate = windows_python if windows_python.exists() else posix_python
                    if not candidate.exists():
                        continue
                    python_executable = str(candidate)
                tools.append(
                    CatalogTool(
                        manifest=manifest,
                        path=tool_dir,
                        python_executable=python_executable,
                    )
                )
        return tools

    def get_enabled(self, name: str) -> CatalogTool | None:
        matches = [tool for tool in self.list_enabled() if tool.manifest.name == name]
        return sorted(matches, key=lambda item: item.manifest.version, reverse=True)[0] if matches else None
