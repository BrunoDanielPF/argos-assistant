from pathlib import Path
import shutil

from assistant.notifications.local import (
    Notification,
    NotificationSink,
)
from assistant.workflows.models import WorkflowHandlerResult


def build_local_workflow_handlers(
    notification_sink: NotificationSink | None = None,
) -> dict:
    sink = notification_sink or NotificationSink(
        Path.home() / ".argos" / "logs" / "notifications.log"
    )

    def noop(arguments: dict) -> dict:
        return dict(arguments)

    def notification_send(arguments: dict) -> dict | WorkflowHandlerResult:
        title = arguments.get("title", "Argos")
        message = arguments.get("message")
        if not isinstance(title, str) or not isinstance(message, str):
            return WorkflowHandlerResult(
                ok=False,
                error="invalid_notification",
            )
        sink.notify(Notification(title=title, message=message))
        return {"notified": True}

    def files_inspect(arguments: dict) -> dict | WorkflowHandlerResult:
        file_path = _path_argument(arguments, "path")
        if file_path is None:
            return WorkflowHandlerResult(
                ok=False,
                error="invalid_path",
            )
        if not file_path.is_file():
            return WorkflowHandlerResult(
                ok=False,
                error="file_not_found",
            )
        stat = file_path.stat()
        return {
            "path": str(file_path),
            "name": file_path.name,
            "suffix": file_path.suffix.lower(),
            "size_bytes": stat.st_size,
        }

    def files_suggest_destination(
        arguments: dict,
    ) -> dict | WorkflowHandlerResult:
        file_path = _path_argument(arguments, "path")
        if file_path is None:
            return WorkflowHandlerResult(
                ok=False,
                error="invalid_path",
            )
        category = _destination_category(file_path.suffix)
        destination = file_path.parent / category / file_path.name
        return {"destination": str(destination)}

    def ask_confirmation(arguments: dict) -> dict:
        return {
            "confirmed": True,
            "message": str(arguments.get("message", "")),
        }

    def files_move(arguments: dict) -> dict | WorkflowHandlerResult:
        source = _path_argument(arguments, "source")
        destination = _path_argument(arguments, "destination")
        if source is None or destination is None:
            return WorkflowHandlerResult(
                ok=False,
                error="invalid_path",
            )
        if not source.is_file():
            return WorkflowHandlerResult(
                ok=False,
                error="file_not_found",
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return {
            "source": str(source),
            "destination": str(destination),
        }

    return {
        "noop": noop,
        "notification.send": notification_send,
        "files.inspect": files_inspect,
        "files.suggest_destination": files_suggest_destination,
        "workflow.ask_confirmation": ask_confirmation,
        "files.move": files_move,
    }


def _path_argument(arguments: dict, name: str) -> Path | None:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        return None
    return Path(value).expanduser()


def _destination_category(suffix: str) -> str:
    normalized = suffix.casefold()
    if normalized == ".pdf":
        return "Documents"
    if normalized in {".md", ".txt", ".rst"}:
        return "Notes"
    return "Organized"
