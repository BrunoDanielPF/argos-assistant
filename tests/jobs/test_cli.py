from typer.testing import CliRunner

from assistant.cli import app
from assistant.jobs.models import JobStatus
from assistant.jobs.repository import JobRepository


def test_cli_jobs_list_shows_recent_jobs(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    repository = JobRepository(database)
    job = repository.create(
        session_id="default",
        run_id="run-1",
        payload={"content": "pesquisar agile"},
    )
    repository.close()
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))

    result = CliRunner().invoke(app, ["jobs", "list"])

    assert result.exit_code == 0
    assert job.job_id[:8] in result.stdout
    assert "queued" in result.stdout
    assert "default" in result.stdout


def test_cli_jobs_show_displays_details(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    repository = JobRepository(database)
    job = repository.create(
        session_id="default",
        run_id="run-1",
        payload={"content": "abrir navegador"},
    )
    repository.close()
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))

    result = CliRunner().invoke(app, ["jobs", "show", job.job_id])

    assert result.exit_code == 0
    assert job.job_id in result.stdout
    assert "run-1" in result.stdout
    assert "abrir navegador" in result.stdout


def test_cli_jobs_show_accepts_unique_prefix(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    repository = JobRepository(database)
    job = repository.create(
        session_id="default",
        run_id="run-1",
        payload={"content": "abrir navegador"},
    )
    repository.close()
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))

    result = CliRunner().invoke(app, ["jobs", "show", job.job_id[:8]])

    assert result.exit_code == 0
    assert job.job_id in result.stdout


def test_cli_jobs_show_reports_missing_job(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(tmp_path / "argos.db"))

    result = CliRunner().invoke(app, ["jobs", "show", "missing"])

    assert result.exit_code == 1
    assert "Job nao encontrado" in result.stdout


def test_cli_jobs_retry_requeues_failed_job(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    repository = JobRepository(database)
    job = repository.create("default", "run-1", {"content": "oi"})
    repository.transition(job.job_id, JobStatus.RUNNING)
    repository.transition(job.job_id, JobStatus.FAILED, error="RuntimeError")
    repository.close()
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))

    result = CliRunner().invoke(app, ["jobs", "retry", job.job_id])

    assert result.exit_code == 0
    assert "queued" in result.stdout
    reopened = JobRepository(database)
    assert reopened.load(job.job_id).status == JobStatus.QUEUED
    reopened.close()


def test_cli_jobs_cancel_cancels_queued_job(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    repository = JobRepository(database)
    job = repository.create("default", "run-1", {"content": "oi"})
    repository.close()
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))

    result = CliRunner().invoke(app, ["jobs", "cancel", job.job_id])

    assert result.exit_code == 0
    assert "cancelled" in result.stdout
