import pytest

from assistant.jobs.models import JobStatus, InvalidJobTransition
from assistant.jobs.repository import JobRepository


def test_repository_creates_and_loads_job(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")

    job = repository.create(
        session_id="default",
        run_id="run-1",
        payload={"content": "pesquisar metodologia agil"},
    )

    loaded = repository.load(job.job_id)

    assert loaded is not None
    assert loaded.job_id == job.job_id
    assert loaded.session_id == "default"
    assert loaded.run_id == "run-1"
    assert loaded.status == JobStatus.QUEUED
    assert loaded.payload == {"content": "pesquisar metodologia agil"}
    assert loaded.attempts == 0
    assert loaded.last_error is None
    assert loaded.created_at <= loaded.updated_at
    repository.close()


def test_repository_persists_jobs_after_reopen(tmp_path):
    database = tmp_path / "argos.db"
    first = JobRepository(database)
    job = first.create(
        session_id="default",
        run_id="run-1",
        payload={"content": "abrir navegador"},
    )
    first.close()

    second = JobRepository(database)

    loaded = second.load(job.job_id)

    assert loaded is not None
    assert loaded.payload["content"] == "abrir navegador"
    second.close()


def test_repository_lists_recent_jobs(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")
    first = repository.create("default", "run-1", {"content": "primeiro"})
    second = repository.create("default", "run-2", {"content": "segundo"})

    jobs = repository.list_recent(limit=10)

    assert [job.job_id for job in jobs] == [second.job_id, first.job_id]
    repository.close()


def test_repository_enforces_valid_transitions(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")
    job = repository.create("default", "run-1", {"content": "executar"})

    running = repository.transition(job.job_id, JobStatus.RUNNING)
    succeeded = repository.transition(running.job_id, JobStatus.SUCCEEDED)

    assert running.status == JobStatus.RUNNING
    assert running.attempts == 1
    assert succeeded.status == JobStatus.SUCCEEDED
    with pytest.raises(InvalidJobTransition):
        repository.transition(succeeded.job_id, JobStatus.RUNNING)
    repository.close()


def test_repository_records_failure_and_retry(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")
    job = repository.create("default", "run-1", {"content": "executar"})

    repository.transition(job.job_id, JobStatus.RUNNING)
    failed = repository.transition(
        job.job_id,
        JobStatus.FAILED,
        error="modelo indisponivel",
    )
    retried = repository.transition(job.job_id, JobStatus.QUEUED)

    assert failed.last_error == "modelo indisponivel"
    assert retried.status == JobStatus.QUEUED
    assert retried.last_error is None
    repository.close()
