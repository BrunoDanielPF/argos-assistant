import ast
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator

from assistant.tools.manifest import ToolManifestError, load_tool_manifest


@dataclass(frozen=True)
class ToolFinding:
    code: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class ToolValidationReport:
    ok: bool
    findings: list[ToolFinding] = field(default_factory=list)


class ToolValidator:
    _blocked_calls = {"eval", "exec", "compile", "__import__"}
    _blocked_imports = {"ctypes"}

    def validate(self, tool_dir: Path) -> ToolValidationReport:
        findings: list[ToolFinding] = []
        try:
            manifest = load_tool_manifest(tool_dir)
        except ToolManifestError as exc:
            return ToolValidationReport(
                ok=False,
                findings=[ToolFinding(code="invalid_manifest", message=str(exc))],
            )

        for name, schema in (
            ("input_schema", manifest.input_schema),
            ("output_schema", manifest.output_schema),
        ):
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as exc:
                findings.append(
                    ToolFinding(code="invalid_schema", message=f"{name}: {exc}")
                )

        entrypoint = Path(tool_dir) / manifest.runtime.entrypoint
        try:
            tree = ast.parse(entrypoint.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            findings.append(ToolFinding(code="invalid_python", message=str(exc)))
            return ToolValidationReport(ok=False, findings=findings)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = self._call_name(node.func)
                if call_name in self._blocked_calls:
                    findings.append(
                        ToolFinding(
                            code="blocked_call",
                            message=f"blocked call: {call_name}",
                        )
                    )
                if call_name in {"subprocess.run", "subprocess.Popen"}:
                    for keyword in node.keywords:
                        if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
                            if keyword.value.value is True:
                                findings.append(
                                    ToolFinding(
                                        code="shell_execution",
                                        message="subprocess shell=True is not allowed",
                                    )
                                )
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                for name in names:
                    if name.split(".", 1)[0] in self._blocked_imports:
                        findings.append(
                            ToolFinding(
                                code="blocked_import",
                                message=f"blocked import: {name}",
                            )
                        )

        return ToolValidationReport(ok=not findings, findings=findings)

    def _call_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = self._call_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""
