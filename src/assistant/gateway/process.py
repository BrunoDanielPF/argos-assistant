from dataclasses import dataclass
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
from time import monotonic, sleep
from typing import Callable

import uvicorn

from assistant.config import AppConfig
from assistant.gateway.app import create_gateway_app
from assistant.gateway.auth import LocalTokenStore
from assistant.gateway.service import GatewayService
from assistant.jobs.repository import JobRepository
from assistant.jobs.scheduler import JobScheduler
from assistant.jobs.worker import JobWorker
from assistant.notifications.local import NotificationSink
from assistant.observability.events import EventLog
from assistant.runtime.factory import RuntimeFactory
from assistant.sessions.repository import SessionRepository


@dataclass(frozen=True)
class GatewayProcessStatus:
    running: bool
    pid: int | None = None


def _process_exists(pid: int) -> bool:
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information,
            False,
            pid,
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle,
                ctypes.byref(exit_code),
            ):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class GatewayProcessManager:
    def __init__(
        self,
        config: AppConfig,
        process_exists: Callable[[int], bool] | None = None,
        process_spawner: Callable | None = None,
    ) -> None:
        self._config = config
        self.pid_file = config.gateway_pid_file
        self._process_exists = process_exists or _process_exists
        self._process_spawner = process_spawner or subprocess.Popen

    def status(self) -> GatewayProcessStatus:
        pid = self._read_pid()
        if pid is None:
            return GatewayProcessStatus(running=False)
        if not self._process_exists(pid):
            self.pid_file.unlink(missing_ok=True)
            return GatewayProcessStatus(running=False)
        return GatewayProcessStatus(running=True, pid=pid)

    def start(self) -> GatewayProcessStatus:
        current = self.status()
        if current.running:
            return current

        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._config.gateway_log_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        creationflags = 0
        if os.name == "nt":
            creationflags = (
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )
        environment = dict(os.environ)
        environment["PYTHONUNBUFFERED"] = "1"
        source_root = str(Path(__file__).resolve().parents[2])
        existing_pythonpath = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            source_root
            if not existing_pythonpath
            else os.pathsep.join([source_root, existing_pythonpath])
        )
        with self._config.gateway_log_file.open(
            "a",
            encoding="utf-8",
        ) as log:
            process = self._process_spawner(
                [sys.executable, "-m", "assistant.gateway.process", "serve"],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                cwd=str(Path.cwd()),
                creationflags=creationflags,
                close_fds=True,
                env=environment,
            )
        self._write_pid(process.pid)
        return GatewayProcessStatus(running=True, pid=process.pid)

    def stop(self, timeout_seconds: float = 10.0) -> GatewayProcessStatus:
        current = self.status()
        if not current.running or current.pid is None:
            return GatewayProcessStatus(running=False)

        os.kill(current.pid, signal.SIGTERM)
        deadline = monotonic() + timeout_seconds
        while monotonic() < deadline:
            if not self._process_exists(current.pid):
                self.pid_file.unlink(missing_ok=True)
                return GatewayProcessStatus(running=False)
            sleep(0.1)
        raise TimeoutError(f"Gateway process {current.pid} did not stop")

    def _read_pid(self) -> int | None:
        if not self.pid_file.exists():
            return None
        try:
            return int(self.pid_file.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            self.pid_file.unlink(missing_ok=True)
            return None

    def _write_pid(self, pid: int) -> None:
        temporary = self.pid_file.with_suffix(self.pid_file.suffix + ".tmp")
        temporary.write_text(str(pid), encoding="ascii")
        temporary.replace(self.pid_file)


def serve() -> None:
    config = AppConfig.load()
    token_store = LocalTokenStore(config.gateway_token_file)
    token_store.get_or_create()
    repository = SessionRepository(config.database_file)
    service = GatewayService(
        RuntimeFactory(config),
        repository,
        event_log=EventLog(config.event_log_file),
    )
    job_repository = JobRepository(config.database_file)
    scheduler = JobScheduler(
        JobWorker(
            job_repository,
            service,
            notifier=NotificationSink(
                config.argos_home / "logs" / "notifications.log"
            ),
        ),
        interval_seconds=config.job_scheduler_interval_seconds,
    )
    app = create_gateway_app(
        service=service,
        token_store=token_store,
        repository=repository,
        model_name=config.model,
        scheduler=scheduler,
    )
    uvicorn.run(
        app,
        host=config.gateway_host,
        port=config.gateway_port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "serve":
        raise SystemExit("Usage: python -m assistant.gateway.process serve")
    serve()
