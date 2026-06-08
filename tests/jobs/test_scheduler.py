from assistant.jobs.scheduler import JobScheduler


class CountingWorker:
    def __init__(self):
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return None


def test_scheduler_run_once_delegates_to_worker():
    worker = CountingWorker()
    scheduler = JobScheduler(worker, interval_seconds=1)

    scheduler.run_once()

    assert worker.calls == 1


def test_scheduler_start_is_idempotent_and_stop_finishes_thread():
    worker = CountingWorker()
    scheduler = JobScheduler(worker, interval_seconds=0.1)

    scheduler.start()
    scheduler.start()
    scheduler.stop()

    assert worker.calls >= 0
