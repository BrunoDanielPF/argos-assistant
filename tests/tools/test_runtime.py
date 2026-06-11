import json
from pathlib import Path
import sys

import pytest
import yaml

from assistant.tools.audit import ToolAuditEvent, ToolAuditLog
from assistant.tools.catalog import CatalogTool
from assistant.tools.manifest import load_tool_manifest
from assistant.tools.permissions import UnsafeToolPermission, expand_permissions
from assistant.tools.runner import ToolRunner

from tests.tools.test_sdk_foundation import valid_manifest


def write_runtime_tool(
    tmp_path: Path,
    handler: str,
    *,
    timeout: int = 5,
    output_schema: dict | None = None,
) -> CatalogTool:
    tool_dir = tmp_path / "tool"
    tool_dir.mkdir()
    payload = valid_manifest()
    payload["execution"]["timeout_seconds"] = timeout
    if output_schema is not None:
        payload["output_schema"] = output_schema
    (tool_dir / "tool.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    (tool_dir / "handler.py").write_text(handler, encoding="utf-8")
    (tool_dir / "requirements.lock").write_text("", encoding="utf-8")
    return CatalogTool(load_tool_manifest(tool_dir), tool_dir)


def test_permission_expansion_uses_validated_argument(tmp_path):
    permissions = valid_manifest()["permissions"]
    permissions["filesystem"]["write"] = ["${directory}/**"]

    effective = expand_permissions(permissions, {"directory": str(tmp_path / "project")})

    assert effective.filesystem_write == [str(tmp_path / "project" / "**")]


def test_permission_expansion_rejects_home_wide_write():
    permissions = valid_manifest()["permissions"]
    permissions["filesystem"]["write"] = ["C:/Users/example/**"]

    with pytest.raises(UnsafeToolPermission):
        expand_permissions(permissions, {})


def test_audit_log_writes_jsonl(tmp_path):
    audit = ToolAuditLog(tmp_path / "audit" / "tools.jsonl")

    audit.write(
        ToolAuditEvent(
            event="execution_started",
            invocation_id="abc",
            tool_name="local.echo",
            tool_version="1.0.0",
        )
    )

    payload = json.loads(audit.path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["invocation_id"] == "abc"


def test_runner_executes_json_protocol(tmp_path):
    tool = write_runtime_tool(
        tmp_path,
        "def run(arguments):\n    return {'text': arguments['text']}\n",
    )

    result = ToolRunner(python_executable=sys.executable).run(tool, {"text": "ola"})

    assert result.ok is True
    assert result.result == {"text": "ola"}


def test_runner_rejects_input_before_process(tmp_path):
    tool = write_runtime_tool(
        tmp_path,
        "def run(arguments):\n    raise RuntimeError('must not run')\n",
    )

    result = ToolRunner(python_executable=sys.executable).run(tool, {"unexpected": True})

    assert result.ok is False
    assert result.error_code == "invalid_arguments"


def test_runner_times_out(tmp_path):
    tool = write_runtime_tool(
        tmp_path,
        "import time\n\ndef run(arguments):\n    time.sleep(2)\n    return {'text': 'late'}\n",
        timeout=1,
    )

    result = ToolRunner(python_executable=sys.executable).run(tool, {"text": "ola"})

    assert result.ok is False
    assert result.error_code == "timeout"
    assert result.retry_safe is True


def test_runner_does_not_mark_write_capable_tool_retry_safe(tmp_path):
    tool = write_runtime_tool(
        tmp_path,
        "import time\n\ndef run(arguments):\n    time.sleep(2)\n    return {'text': 'late'}\n",
        timeout=1,
    )
    tool.manifest.permissions.filesystem.write.append("${text}")

    result = ToolRunner(python_executable=sys.executable).run(
        tool,
        {"text": "ola"},
    )

    assert result.ok is False
    assert result.retry_safe is False


def test_runner_rejects_invalid_output_schema(tmp_path):
    tool = write_runtime_tool(
        tmp_path,
        "def run(arguments):\n    return {'wrong': True}\n",
    )

    result = ToolRunner(python_executable=sys.executable).run(tool, {"text": "ola"})

    assert result.ok is False
    assert result.error_code == "invalid_output"


def test_runner_audits_execution(tmp_path):
    tool = write_runtime_tool(
        tmp_path,
        "def run(arguments):\n    return {'text': arguments['text']}\n",
    )
    audit = ToolAuditLog(tmp_path / "audit.jsonl")

    result = ToolRunner(
        python_executable=sys.executable,
        audit_log=audit,
    ).run(tool, {"text": "ola"})

    events = [
        json.loads(line)["event"]
        for line in audit.path.read_text(encoding="utf-8").splitlines()
    ]
    assert result.ok is True
    assert events == ["execution_started", "execution_finished"]
