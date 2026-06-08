from threading import Event, Thread

from assistant.jobs.models import JobRecord
from assistant.jobs.worker import JobWorker


class JobScheduler:
    def __init__(
        self,
        worker: JobWorker,
        interval_seconds: float = 5.0,
    ) -> None:
        self._worker = worker
        self._interval_seconds = max(0.1, interval_seconds)
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run_loop,
            name="argos-job-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_seconds)

    def run_once(self) -> JobRecord | None:
        return self._worker.run_once()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.run_once()
            self._stop_event.wait(self._interval_seconds)
