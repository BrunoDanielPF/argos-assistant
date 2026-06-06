from pathlib import Path

import pytest

from assistant.tools.manifest import ToolManifestError, load_tool_manifest
from assistant.tools.models import ToolManifest
from assistant.tools.validator import ToolValidator


def valid_manifest() -> dict:
    return {
        "schema_version": "1.0",
        "name": "local.echo",
        "version": "1.0.0",
        "title": "Echo",
        "description": "Retorna o texto informado.",
        "runtime": {
            "type": "python",
            "python": ">=3.12,<3.13",
            "entrypoint": "handler.py",
        },
        "input_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["text"],
            "properties": {"text": {"type": "string"}},
        },
        "output_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["text"],
            "properties": {"text": {"type": "string"}},
        },
        "permissions": {
            "filesystem": {"read": [], "write": []},
            "network": {"enabled": False, "hosts": []},
            "subprocess": {"executables": []},
        },
        "execution": {"timeout_seconds": 30, "max_output_bytes": 65536},
    }


def write_tool(tmp_path: Path, manifest: dict | None = None, handler: str | None = None) -> Path:
    import yaml

    tool_dir = tmp_path / "tool"
    tool_dir.mkdir()
    (tool_dir / "tool.yaml").write_text(
        yaml.safe_dump(manifest or valid_manifest(), sort_keys=False),
        encoding="utf-8",
    )
    (tool_dir / "handler.py").write_text(
        handler or "def run(arguments):\n    return {'text': arguments['text']}\n",
        encoding="utf-8",
    )
    (tool_dir / "requirements.lock").write_text("", encoding="utf-8")
    return tool_dir


def test_tool_manifest_parses_strict_contract():
    manifest = ToolManifest.model_validate(valid_manifest())

    assert manifest.name == "local.echo"
    assert manifest.permissions.network.enabled is False


def test_manifest_rejects_unknown_fields():
    payload = valid_manifest()
    payload["unexpected"] = True

    with pytest.raises(ValueError):
        ToolManifest.model_validate(payload)


def test_loader_rejects_entrypoint_traversal(tmp_path):
    payload = valid_manifest()
    payload["runtime"]["entrypoint"] = "../evil.py"
    tool_dir = write_tool(tmp_path, payload)

    with pytest.raises(ToolManifestError, match="entrypoint"):
        load_tool_manifest(tool_dir)


def test_validator_rejects_dangerous_python(tmp_path):
    tool_dir = write_tool(
        tmp_path,
        handler="def run(arguments):\n    return eval(arguments['text'])\n",
    )

    report = ToolValidator().validate(tool_dir)

    assert report.ok is False
    assert any("eval" in finding.message for finding in report.findings)


def test_validator_accepts_safe_tool(tmp_path):
    tool_dir = write_tool(tmp_path)

    report = ToolValidator().validate(tool_dir)

    assert report.ok is True
