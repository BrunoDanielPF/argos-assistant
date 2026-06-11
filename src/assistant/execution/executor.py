from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
from uuid import uuid4
import webbrowser

from assistant.tools.permissions import UnsafeToolPermission, expand_permissions


@dataclass
class ExecutionResult:
    ok: bool
    message: str
    data: dict | None = None
    error_code: str | None = None
    retry_safe: bool = False


KNOWN_APPLICATIONS = {
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "notepad": "notepad.exe",
    "editor": "notepad.exe",
}


class ActionExecutor:
    def __init__(
        self,
        open_url_fn=None,
        open_application_fn=None,
        open_file_fn=None,
        tool_catalog=None,
        tool_runner=None,
        job_repository=None,
    ) -> None:
        self._open_url = open_url_fn or webbrowser.open
        self._open_application = open_application_fn or self._default_open_application
        self._open_file = open_file_fn or self._default_open_file
        self._tool_catalog = tool_catalog
        self._tool_runner = tool_runner
        self._job_repository = job_repository

    def configure_tools(self, tool_catalog, tool_runner) -> None:
        self._tool_catalog = tool_catalog
        self._tool_runner = tool_runner

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

        if capability_name == "create_file":
            path = args.get("path")
            content = args.get("content", "")
            if not isinstance(path, str) or not path.strip():
                return ExecutionResult(ok=False, message="Missing path for create_file")
            if not isinstance(content, str):
                return ExecutionResult(ok=False, message="Invalid content for create_file")

            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return ExecutionResult(
                ok=True,
                message=f"Created file {file_path}",
                data={"path": str(file_path)},
            )

        if capability_name == "write_file":
            path = args.get("path")
            content = args.get("content")
            write_mode = args.get("write_mode")
            if not isinstance(path, str) or not path.strip():
                return ExecutionResult(ok=False, message="Missing path for write_file")
            if not isinstance(content, str):
                return ExecutionResult(ok=False, message="Invalid content for write_file")
            if write_mode not in {"replace", "append"}:
                return ExecutionResult(ok=False, message="Invalid write mode for write_file")

            file_path = Path(path)
            if not file_path.is_file():
                return ExecutionResult(ok=False, message=f"File not found: {path}")

            if write_mode == "replace":
                updated_content = content
            else:
                current_content = file_path.read_text(encoding="utf-8")
                separator = "" if not current_content or current_content.endswith("\n") else "\n"
                updated_content = f"{current_content}{separator}{content}"
            file_path.write_text(updated_content, encoding="utf-8")
            return ExecutionResult(
                ok=True,
                message=f"Updated file {file_path}",
                data={"path": str(file_path), "write_mode": write_mode},
            )

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

        if capability_name == "schedule_reminder":
            if self._job_repository is None:
                return ExecutionResult(
                    ok=False,
                    message="Reminder scheduling is not configured",
                )
            content = args.get("content")
            scheduled_for = args.get("scheduled_for")
            session_id = args.get("session_id", "default")
            if not isinstance(content, str) or not content.strip():
                return ExecutionResult(
                    ok=False,
                    message="Missing content for schedule_reminder",
                )
            if not isinstance(scheduled_for, str) or not scheduled_for.strip():
                return ExecutionResult(
                    ok=False,
                    message="Missing scheduled_for for schedule_reminder",
                )
            try:
                due_at = datetime.fromisoformat(
                    scheduled_for.replace("Z", "+00:00")
                )
            except ValueError:
                return ExecutionResult(
                    ok=False,
                    message="Invalid scheduled_for for schedule_reminder",
                )
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=timezone.utc)
            due_at = due_at.astimezone(timezone.utc)
            if not isinstance(session_id, str) or not session_id.strip():
                session_id = "default"
            job = self._job_repository.create(
                session_id=session_id,
                run_id=str(uuid4()),
                payload={
                    "type": "reminder",
                    "content": f"Lembrete: {content.strip()}",
                },
                scheduled_for=due_at,
            )
            return ExecutionResult(
                ok=True,
                message=(
                    "Lembrete agendado para "
                    f"{due_at.astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} "
                    f"(job {job.job_id[:8]})."
                ),
                data={
                    "job_id": job.job_id,
                    "scheduled_for": due_at.isoformat(),
                },
            )

        if self._tool_catalog is not None and self._tool_runner is not None:
            tool = self._tool_catalog.get_enabled(capability_name)
            if tool is not None:
                try:
                    expand_permissions(tool.manifest.permissions, args)
                except UnsafeToolPermission as exc:
                    return ExecutionResult(
                        ok=False,
                        message=f"Unsafe tool permissions: {exc}",
                    )
                result = self._tool_runner.run(tool, args)
                if result.ok:
                    return ExecutionResult(
                        ok=True,
                        message=f"Tool {capability_name} executed successfully",
                        data=result.result,
                    )
                return ExecutionResult(
                    ok=False,
                    message=f"Tool {capability_name} failed: {result.message}",
                    error_code=result.error_code,
                    retry_safe=result.retry_safe,
                )

        return ExecutionResult(
            ok=False, message=f"Unsupported capability: {capability_name}"
        )
