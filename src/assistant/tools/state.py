from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from tempfile import NamedTemporaryFile


class InvalidToolTransition(ValueError):
    pass


@dataclass
class ToolStateRecord:
    name: str
    version: str
    state: str
    hashes: dict[str, str]


ALLOWED_TRANSITIONS = {
    "draft": {"validating", "rejected"},
    "validating": {"validated", "rejected"},
    "validated": {"approved", "rejected"},
    "approved": {"installed", "rejected"},
    "installed": {"enabled", "disabled", "broken"},
    "enabled": {"disabled", "broken"},
    "disabled": {"enabled", "broken"},
    "broken": {"validated", "rejected"},
    "rejected": set(),
}


def hash_tool_files(tool_dir: Path) -> dict[str, str]:
    hashes = {}
    for filename in ("tool.yaml", "handler.py", "requirements.lock"):
        path = Path(tool_dir) / filename
        if path.is_file():
            hashes[filename] = sha256(path.read_bytes()).hexdigest()
    return hashes


class ToolStateStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def register_draft(
        self,
        name: str,
        version: str,
        hashes: dict[str, str],
    ) -> ToolStateRecord:
        records = self._load()
        record = ToolStateRecord(name=name, version=version, state="draft", hashes=dict(hashes))
        records[self._key(name, version)] = asdict(record)
        self._save(records)
        return record

    def transition(self, name: str, version: str, target: str) -> ToolStateRecord:
        records = self._load()
        key = self._key(name, version)
        if key not in records:
            raise KeyError(key)
        current = records[key]["state"]
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            raise InvalidToolTransition(f"cannot transition {current} -> {target}")
        records[key]["state"] = target
        self._save(records)
        return ToolStateRecord(**records[key])

    def get(self, name: str, version: str) -> ToolStateRecord | None:
        payload = self._load().get(self._key(name, version))
        return ToolStateRecord(**payload) if payload else None

    def verify_integrity(
        self,
        name: str,
        version: str,
        current_hashes: dict[str, str],
    ) -> ToolStateRecord:
        record = self.get(name, version)
        if record is None:
            raise KeyError(self._key(name, version))
        if record.hashes != current_hashes and record.state not in {"draft", "validating"}:
            records = self._load()
            records[self._key(name, version)]["state"] = "broken"
            self._save(records)
            return ToolStateRecord(**records[self._key(name, version)])
        return record

    def _key(self, name: str, version: str) -> str:
        return f"{name}@{version}"

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self, records: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._path.parent,
            delete=False,
        ) as temp:
            json.dump(records, temp, indent=2, sort_keys=True)
            temp_path = Path(temp.name)
        temp_path.replace(self._path)
