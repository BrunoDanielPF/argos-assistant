from pathlib import Path

from assistant.workflows.handlers import build_local_workflow_handlers
from assistant.workflows.models import WorkflowHandlerResult


class FakeNotificationSink:
    def __init__(self):
        self.notifications = []

    def notify(self, notification):
        self.notifications.append(notification)


def test_local_handlers_do_not_register_shell():
    handlers = build_local_workflow_handlers()

    assert "shell.run" not in handlers
    assert {
        "noop",
        "notification.send",
        "files.inspect",
        "files.suggest_destination",
        "workflow.ask_confirmation",
        "files.move",
    }.issubset(handlers)


def test_notification_handler_uses_injected_sink():
    sink = FakeNotificationSink()
    handler = build_local_workflow_handlers(notification_sink=sink)[
        "notification.send"
    ]

    result = handler({"title": "Argos", "message": "Revise tarefas"})

    assert result == {"notified": True}
    assert sink.notifications[0].title == "Argos"
    assert sink.notifications[0].message == "Revise tarefas"


def test_files_inspect_returns_metadata(tmp_path):
    file_path = tmp_path / "notes.md"
    file_path.write_text("# Notes", encoding="utf-8")
    handler = build_local_workflow_handlers()["files.inspect"]

    result = handler({"path": str(file_path)})

    assert result["path"] == str(file_path)
    assert result["name"] == "notes.md"
    assert result["suffix"] == ".md"
    assert result["size_bytes"] == len("# Notes")


def test_files_suggest_destination_is_non_destructive(tmp_path):
    file_path = tmp_path / "report.pdf"
    file_path.write_bytes(b"pdf")
    handler = build_local_workflow_handlers()["files.suggest_destination"]

    result = handler({"path": str(file_path)})

    assert Path(result["destination"]).name == "report.pdf"
    assert Path(result["destination"]).parent.name == "Documents"
    assert file_path.exists()


def test_files_move_moves_file_after_runner_authorization(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("data", encoding="utf-8")
    destination = tmp_path / "archive" / "source.txt"
    handler = build_local_workflow_handlers()["files.move"]

    result = handler(
        {"source": str(source), "destination": str(destination)}
    )

    assert result == {
        "source": str(source),
        "destination": str(destination),
    }
    assert destination.read_text(encoding="utf-8") == "data"
    assert not source.exists()


def test_file_handler_returns_safe_failure_for_missing_path(tmp_path):
    handler = build_local_workflow_handlers()["files.inspect"]

    result = handler({"path": str(tmp_path / "missing.txt")})

    assert isinstance(result, WorkflowHandlerResult)
    assert result.ok is False
    assert result.error == "file_not_found"
