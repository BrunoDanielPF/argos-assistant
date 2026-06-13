from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil

import yaml

from assistant.tools.state import ToolStateStore, hash_tool_files
from assistant.tools.validator import ToolValidator


class InvalidToolName(ValueError):
    pass


@dataclass(frozen=True)
class GeneratedToolDraft:
    path: Path
    state: str
    can_execute: bool = False


class ToolDraftGenerator:
    _name_pattern = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*)+$")

    def __init__(self, drafts_root: Path, state_store: ToolStateStore) -> None:
        self._drafts_root = Path(drafts_root)
        self._state_store = state_store

    def generate(self, definition: dict) -> GeneratedToolDraft:
        name = definition.get("name")
        version = definition.get("version", "1.0.0")
        if not isinstance(name, str) or not self._name_pattern.fullmatch(name):
            raise InvalidToolName(str(name))
        draft_dir = self._drafts_root / name / version
        definition_hash = sha256(
            json.dumps(
                definition,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if draft_dir.exists():
            hash_file = draft_dir / ".definition-hash"
            record = self._state_store.get(name, version)
            if (
                hash_file.is_file()
                and hash_file.read_text(encoding="ascii").strip()
                == definition_hash
                and record is not None
                and record.state == "validated"
            ):
                return GeneratedToolDraft(
                    path=draft_dir,
                    state=record.state,
                )
            raise FileExistsError(draft_dir)
        draft_dir.mkdir(parents=True)
        (draft_dir / ".definition-hash").write_text(
            definition_hash,
            encoding="ascii",
        )
        manifest = {
            "schema_version": "1.0",
            "name": name,
            "version": version,
            "title": definition.get("title", name),
            "description": definition.get("description", "Generated Argos tool."),
            "runtime": {
                "type": "python",
                "python": ">=3.12,<3.13",
                "entrypoint": "handler.py",
            },
            "input_schema": definition.get(
                "input_schema",
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "additionalProperties": False,
                },
            ),
            "output_schema": definition.get(
                "output_schema",
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "additionalProperties": False,
                },
            ),
            "permissions": definition.get(
                "permissions",
                {
                    "filesystem": {"read": [], "write": []},
                    "network": {"enabled": False, "hosts": []},
                    "subprocess": {"executables": []},
                },
            ),
            "execution": definition.get(
                "execution",
                {"timeout_seconds": 60, "max_output_bytes": 1_048_576},
            ),
        }
        (draft_dir / "tool.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False),
            encoding="utf-8",
        )
        (draft_dir / "handler.py").write_text(
            definition.get(
                "handler_body",
                "def run(arguments):\n    raise NotImplementedError('draft tool')\n",
            ),
            encoding="utf-8",
        )
        (draft_dir / "requirements.lock").write_text("", encoding="utf-8")
        (draft_dir / "tests").mkdir()
        (draft_dir / "tests" / "test_handler.py").write_text(
            "def test_draft_requires_review():\n    assert True\n",
            encoding="utf-8",
        )

        self._state_store.register_draft(name, version, hash_tool_files(draft_dir))
        self._state_store.transition(name, version, "validating")
        report = ToolValidator().validate(draft_dir)
        report_payload = {
            "ok": report.ok,
            "findings": [
                {
                    "code": finding.code,
                    "message": finding.message,
                    "severity": finding.severity,
                }
                for finding in report.findings
            ],
        }
        (draft_dir / "validation-report.json").write_text(
            json.dumps(report_payload, indent=2),
            encoding="utf-8",
        )
        target_state = "validated" if report.ok else "rejected"
        record = self._state_store.transition(name, version, target_state)
        return GeneratedToolDraft(path=draft_dir, state=record.state)

    def remove_quarantined(
        self,
        *,
        name: str,
        version: str,
        draft_path: Path,
    ) -> bool:
        root = self._drafts_root.resolve()
        target = Path(draft_path).resolve()
        if root not in target.parents:
            raise ValueError("draft path is outside quarantine")
        record = self._state_store.get(name, version)
        if record is None or record.state not in {"validated", "rejected"}:
            return False
        if record.state == "validated":
            self._state_store.transition(name, version, "rejected")
        if target.is_dir():
            shutil.rmtree(target)
        return True
