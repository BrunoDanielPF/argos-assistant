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
    _read_only_imports = {
        "datetime",
        "hashlib",
        "json",
        "math",
        "os",
        "pathlib",
        "platform",
        "re",
        "stat",
        "statistics",
        "time",
    }
    _read_only_calls = {
        "Path",
        "bool",
        "datetime.fromtimestamp",
        "float",
        "getattr",
        "hasattr",
        "int",
        "isoformat",
        "len",
        "max",
        "min",
        "os.path.abspath",
        "os.path.exists",
        "os.path.getctime",
        "os.path.getmtime",
        "os.path.isfile",
        "os.stat",
        "platform.system",
        "resolve",
        "stat",
        "str",
    }

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

    def validate_read_only_source(
        self,
        source: str,
    ) -> ToolValidationReport:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return ToolValidationReport(
                ok=False,
                findings=[
                    ToolFinding(
                        code="invalid_python",
                        message=str(exc),
                    )
                ],
            )

        findings: list[ToolFinding] = []
        run_functions = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                findings.extend(self._validate_read_only_import(node))
                continue
            if isinstance(node, ast.FunctionDef) and node.name == "run":
                run_functions.append(node)
                continue
            findings.append(
                ToolFinding(
                    code="top_level_effect",
                    message="only imports and run(arguments) are allowed",
                )
            )

        if len(run_functions) != 1:
            findings.append(
                ToolFinding(
                    code="invalid_entrypoint",
                    message="exactly one run(arguments) function is required",
                )
            )
        else:
            run_function = run_functions[0]
            if (
                len(run_function.args.args) != 1
                or run_function.args.args[0].arg != "arguments"
                or run_function.args.vararg is not None
                or run_function.args.kwarg is not None
                or run_function.decorator_list
            ):
                findings.append(
                    ToolFinding(
                        code="invalid_entrypoint",
                        message="run must accept only arguments",
                    )
                )
            for node in ast.walk(run_function):
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    targets = (
                        node.targets
                        if isinstance(node, ast.Assign)
                        else [node.target]
                    )
                    if any(
                        isinstance(target, (ast.Attribute, ast.Subscript))
                        for target in targets
                    ):
                        findings.append(
                            ToolFinding(
                                code="external_assignment",
                                message="assignments to attributes or subscripts are not allowed",
                            )
                        )
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    findings.append(
                        ToolFinding(
                            code="dynamic_import",
                            message="imports inside run are not allowed",
                        )
                    )
                if isinstance(node, ast.Call):
                    call_name = self._call_name(node.func)
                    if call_name not in self._read_only_calls:
                        findings.append(
                            ToolFinding(
                                code="unknown_call",
                                message=f"unknown call: {call_name}",
                            )
                        )
                if isinstance(node, (ast.Delete, ast.Global, ast.Nonlocal)):
                    findings.append(
                        ToolFinding(
                            code="mutation_not_allowed",
                            message=type(node).__name__,
                        )
                    )
                if isinstance(node, (ast.With, ast.AsyncWith)):
                    findings.append(
                        ToolFinding(
                            code="context_manager_not_allowed",
                            message="context managers are not allowed",
                        )
                    )

        unique = {
            (finding.code, finding.message): finding
            for finding in findings
        }
        return ToolValidationReport(
            ok=not unique,
            findings=list(unique.values()),
        )

    def _validate_read_only_import(
        self,
        node: ast.Import | ast.ImportFrom,
    ) -> list[ToolFinding]:
        names = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
        return [
            ToolFinding(
                code="import_not_allowed",
                message=f"import not allowed: {name}",
            )
            for name in names
            if name.split(".", 1)[0] not in self._read_only_imports
        ]

    def _call_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = self._call_name(node.value)
            return f"{prefix}.{node.attr}" if prefix else node.attr
        return ""
