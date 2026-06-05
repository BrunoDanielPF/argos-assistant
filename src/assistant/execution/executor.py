from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import webbrowser


@dataclass
class ExecutionResult:
    ok: bool
    message: str
    data: dict | None = None


KNOWN_APPLICATIONS = {
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "notepad": "notepad.exe",
    "editor": "notepad.exe",
}


class ActionExecutor:
    def __init__(self, open_url_fn=None, open_application_fn=None, open_file_fn=None) -> None:
        self._open_url = open_url_fn or webbrowser.open
        self._open_application = open_application_fn or self._default_open_application
        self._open_file = open_file_fn or self._default_open_file

    def _default_open_application(self, application: str) -> None:
        if hasattr(os, "startfile"):
            os.startfile(application)
            return
        subprocess.Popen([application])

    def _default_open_file(self, path: str) -> None:
        if hasattr(os, "startfile"):
            os.startfile(path)
            return
        subprocess.Popen([path])

    def execute(self, capability_name: str, args: dict) -> ExecutionResult:
        if capability_name == "open_application":
            application = args.get("application", args.get("app", args.get("name")))
            if not isinstance(application, str) or not application.strip():
                return ExecutionResult(
                    ok=False, message="Missing application name for open_application"
                )
            normalized_application = KNOWN_APPLICATIONS.get(application.strip().lower(), application)
            self._open_application(normalized_application)
            return ExecutionResult(ok=True, message=f"Opened application {application}")

        if capability_name == "open_url":
            url = args["url"]
            self._open_url(url)
            return ExecutionResult(ok=True, message=f"Opened {url}")

        if capability_name == "open_file":
            path = args.get("path")
            if not isinstance(path, str) or not path.strip():
                return ExecutionResult(ok=False, message="Missing path for open_file")

            file_path = Path(path)
            if not file_path.exists():
                return ExecutionResult(ok=False, message=f"File not found: {path}")

            self._open_file(str(file_path))
            return ExecutionResult(ok=True, message=f"Opened file {file_path}")

        if capability_name == "search_files":
            root = Path(args["root"])
            pattern = args["pattern"]
            max_results = args.get("max_results", 5)
            if not isinstance(max_results, int) or max_results <= 0:
                max_results = 5

            matches = sorted(str(path) for path in root.rglob(pattern))
            if not matches:
                return ExecutionResult(
                    ok=False,
                    message=f"No files matched '{pattern}' under '{root}'",
                )

            visible_matches = matches[:max_results]
            lines = [f"Found {len(matches)} match{'es' if len(matches) != 1 else ''} for '{pattern}':"]
            lines.extend(f"- {path}" for path in visible_matches)
            if len(matches) > max_results:
                lines.append(f"Showing first {max_results}.")
            return ExecutionResult(
                ok=True,
                message="\n".join(lines),
                data={"matches": visible_matches, "all_count": len(matches)},
            )

        return ExecutionResult(
            ok=False, message=f"Unsupported capability: {capability_name}"
        )
