import hmac
import os
from pathlib import Path
import secrets
import stat
import subprocess
from typing import Callable


class TokenProtectionError(RuntimeError):
    pass


def _harden_permissions(path: Path) -> None:
    if os.name == "nt":
        username = os.environ.get("USERNAME")
        if not username:
            raise OSError("USERNAME is not available")
        result = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                f"{username}:R",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or "icacls failed")
        return
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


class LocalTokenStore:
    def __init__(
        self,
        path: Path,
        permission_hardener: Callable[[Path], None] | None = None,
    ) -> None:
        self.path = path
        self._permission_hardener = permission_hardener or _harden_permissions

    def get_or_create(self) -> str:
        if self.path.exists():
            return self.path.read_text(encoding="ascii").strip()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(32)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(token, encoding="ascii")
        try:
            temporary.replace(self.path)
            self._permission_hardener(self.path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            self.path.unlink(missing_ok=True)
            raise TokenProtectionError(
                f"Could not protect gateway token file: {self.path}"
            ) from exc
        return token

    def verify(self, candidate: str) -> bool:
        if not self.path.exists():
            return False
        expected = self.path.read_text(encoding="ascii").strip()
        return hmac.compare_digest(expected, candidate)
