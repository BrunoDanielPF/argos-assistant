from pathlib import Path
import shutil
import subprocess
import venv

from assistant.tools.manifest import load_tool_manifest
from assistant.tools.state import ToolStateStore


class ToolApprovalRequired(PermissionError):
    pass


class InvalidRequirementsLock(ValueError):
    pass


class ToolInstaller:
    def __init__(
        self,
        tools_root: Path,
        envs_root: Path,
        state_store: ToolStateStore,
        create_environment: bool = True,
        command_runner=None,
    ) -> None:
        self._tools_root = Path(tools_root)
        self._envs_root = Path(envs_root)
        self._state_store = state_store
        self._create_environment = create_environment
        self._command_runner = command_runner or self._run_command

    def install(self, source_dir: Path) -> Path:
        source_dir = Path(source_dir)
        manifest = load_tool_manifest(source_dir)
        record = self._state_store.get(manifest.name, manifest.version)
        if record is None or record.state != "approved":
            raise ToolApprovalRequired(f"{manifest.name}@{manifest.version}")

        target = self._tools_root / manifest.name / manifest.version
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target)

        lock = target / "requirements.lock"
        requirements = [
            line.strip()
            for line in lock.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        env_dir = self._envs_root / f"{manifest.name}-{manifest.version}"
        if self._create_environment:
            venv.EnvBuilder(with_pip=True).create(env_dir)
        if requirements:
            if any("--hash=sha256:" not in line for line in requirements):
                shutil.rmtree(target)
                raise InvalidRequirementsLock("all dependencies must include sha256 hashes")
            python = (
                env_dir / "Scripts" / "python.exe"
                if (env_dir / "Scripts").exists()
                else env_dir / "bin" / "python"
            )
            self._command_runner(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--require-hashes",
                    "--only-binary",
                    ":all:",
                    "-r",
                    str(lock),
                ]
            )

        self._state_store.transition(manifest.name, manifest.version, "installed")
        return target

    def _run_command(self, command: list[str]) -> None:
        subprocess.run(command, check=True, shell=False)
