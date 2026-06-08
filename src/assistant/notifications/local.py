from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class Notification:
    title: str
    message: str


class NotificationSink:
    def __init__(
        self,
        log_file: Path,
        command_runner=None,
    ) -> None:
        self._log_file = log_file
        self._command_runner = command_runner or subprocess.run

    def notify(self, notification: Notification) -> None:
        self._write_log(notification)
        self._try_windows_balloon(notification)

    def _write_log(self, notification: Notification) -> None:
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        with self._log_file.open("a", encoding="utf-8") as stream:
            stream.write(f"{notification.title}: {notification.message}\n")

    def _try_windows_balloon(self, notification: Notification) -> None:
        escaped_title = notification.title.replace("'", "''")
        escaped_message = notification.message.replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.Visible = $true; "
            f"$n.ShowBalloonTip(5000, '{escaped_title}', '{escaped_message}', "
            "[System.Windows.Forms.ToolTipIcon]::Info); "
            "Start-Sleep -Seconds 1; "
            "$n.Dispose();"
        )
        try:
            self._command_runner(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                check=False,
                timeout=3,
                capture_output=True,
            )
        except Exception:
            return
