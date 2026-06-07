from datetime import datetime, timedelta, timezone

from assistant.jobs.models import JobStatus
from assistant.jobs.repository import JobRepository
from assistant.jobs.worker import JobWorker
from assistant.runtime.contracts import AgentResponse, ConfirmationRequest


class RecordingService:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def handle(self, request):
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_worker_executes_next_queued_job_successfully(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")
    job = repository.create(
        session_id="default",
        run_id="run-1",
        payload={"content": "oi", "cwd": "C:\\workspace"},
    )
    service = RecordingService(
        AgentResponse(
            session_id="default",
            run_id="run-1",
            ok=True,
            message="ok",
        )
    )

    processed = JobWorker(repository, service).run_once()

    loaded = repository.load(job.job_id)
    assert processed is not None
    assert loaded.status == JobStatus.SUCCEEDED
    assert loaded.attempts == 1
    assert service.requests[0].content == "oi"
    assert service.requests[0].cwd == "C:\\workspace"
    repository.close()


def test_worker_marks_job_failed_with_safe_error(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")
    job = repository.create("default", "run-1", {"content": "oi"})
    service = RecordingService(RuntimeError("segredo interno"))

    JobWorker(repository, service).run_once()

    loaded = repository.load(job.job_id)
    assert loaded.status == JobStatus.FAILED
    assert loaded.last_error == "RuntimeError"
    assert "segredo" not in loaded.last_error
    repository.close()


def test_worker_pauses_job_waiting_for_confirmation(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")
    job = repository.create("default", "run-1", {"content": "crie arquivo"})
    service = RecordingService(
        AgentResponse(
            session_id="default",
            run_id="run-1",
            ok=False,
            status="waiting_confirmation",
            message="Preciso de confirmacao.",
            confirmation=ConfirmationRequest(
                confirmation_id="confirm-1",
                capability="create_file",
                arguments_summary={"path": "C:\\temp\\a.md"},
                permissions=["write:C:\\temp\\a.md"],
                question="Autorizar?",
            ),
        )
    )

    JobWorker(repository, service).run_once()

    loaded = repository.load(job.job_id)
    assert loaded.status == JobStatus.WAITING_CONFIRMATION
    assert loaded.attempts == 1
    repository.close()


def test_worker_returns_none_when_no_queued_jobs(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")

    processed = JobWorker(repository, RecordingService(None)).run_once()

    assert processed is None
    repository.close()


def test_worker_does_not_execute_future_scheduled_job(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")
    repository.create(
        session_id="default",
        run_id="run-1",
        payload={"content": "lembrete"},
        scheduled_for=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    service = RecordingService(
        AgentResponse(session_id="default", run_id="run-1", ok=True, message="ok")
    )

    processed = JobWorker(repository, service).run_once()

    assert processed is None
    assert service.requests == []
    repository.close()
