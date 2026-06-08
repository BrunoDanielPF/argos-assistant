from assistant.notifications.local import Notification, NotificationSink


def test_notification_sink_writes_log_and_ignores_command_failure(tmp_path):
    calls = []

    def failing_runner(*args, **kwargs):
        calls.append((args, kwargs))
        raise OSError("powershell unavailable")

    sink = NotificationSink(
        tmp_path / "notifications.log",
        command_runner=failing_runner,
    )

    sink.notify(Notification(title="Argos", message="Lembrete: teste"))

    assert "Argos: Lembrete: teste" in (
        tmp_path / "notifications.log"
    ).read_text(encoding="utf-8")
    assert calls
