from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

from jsonschema import Draft202012Validator

from assistant.tools.audit import ToolAuditEvent, ToolAuditLog
from assistant.tools.catalog import CatalogTool


@dataclass(frozen=True)
class ToolRunResult:
    ok: bool
    result: dict | None = None
    error_code: str | None = None
    message: str = ""


class ToolRunner:
    def __init__(
        self,
        python_executable: str | None = None,
        audit_log: ToolAuditLog | None = None,
    ) -> None:
        self._python = python_executable or sys.executable
        self._audit_log = audit_log

    def run(self, tool: CatalogTool, arguments: dict) -> ToolRunResult:
        manifest = tool.manifest
        errors = list(Draft202012Validator(manifest.input_schema).iter_errors(arguments))
        if errors:
            return ToolRunResult(
                ok=False,
                error_code="invalid_arguments",
                message=errors[0].message,
            )

        request = {
            "protocol_version": "1.0",
            "tool": manifest.name,
            "invocation_id": str(uuid4()),
            "arguments": arguments,
        }
        self._audit("execution_started", request["invocation_id"], tool)
        bootstrap = Path(__file__).with_name("bootstrap.py")
        entrypoint = tool.path / manifest.runtime.entrypoint
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
        }
        try:
            python_executable = tool.python_executable or self._python
            with TemporaryDirectory(prefix="argos-tool-") as temp_dir:
                process = subprocess.run(
                    [python_executable, "-I", str(bootstrap), str(entrypoint)],
                    input=json.dumps(request),
                    text=True,
                    capture_output=True,
                    shell=False,
                    cwd=temp_dir,
                    env=environment,
                    timeout=manifest.execution.timeout_seconds,
                    check=False,
                )
        except subprocess.TimeoutExpired:
            self._audit(
                "execution_failed",
                request["invocation_id"],
                tool,
                {"code": "timeout"},
            )
            return ToolRunResult(ok=False, error_code="timeout", message="tool timed out")

        output_bytes = process.stdout.encode("utf-8", errors="replace")
        if len(output_bytes) > manifest.execution.max_output_bytes:
            return ToolRunResult(
                ok=False,
                error_code="output_limit",
                message="tool output exceeded limit",
            )
        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError:
            return ToolRunResult(
                ok=False,
                error_code="invalid_output",
                message="tool returned invalid JSON",
            )
        if payload.get("ok") is not True:
            error = payload.get("error") or {}
            return ToolRunResult(
                ok=False,
                error_code=error.get("code", "tool_error"),
                message=error.get("message", "tool failed"),
            )
        result = payload.get("result")
        errors = list(Draft202012Validator(manifest.output_schema).iter_errors(result))
        if errors:
            self._audit(
                "execution_failed",
                request["invocation_id"],
                tool,
                {"code": "invalid_output"},
            )
            return ToolRunResult(
                ok=False,
                error_code="invalid_output",
                message=errors[0].message,
            )
        self._audit("execution_finished", request["invocation_id"], tool)
        return ToolRunResult(ok=True, result=result)

    def _audit(
        self,
        event: str,
        invocation_id: str,
        tool: CatalogTool,
        details: dict | None = None,
    ) -> None:
        if self._audit_log is None:
            return
        self._audit_log.write(
            ToolAuditEvent(
                event=event,
                invocation_id=invocation_id,
                tool_name=tool.manifest.name,
                tool_version=tool.manifest.version,
                details=details or {},
            )
        )
