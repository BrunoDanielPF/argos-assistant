from assistant.jobs.models import JobRecord, JobStatus
from assistant.jobs.repository import JobRepository
from assistant.runtime.contracts import AgentRequest


class JobWorker:
    def __init__(
        self,
        repository: JobRepository,
        service,
    ) -> None:
        self._repository = repository
        self._service = service

    def run_once(self) -> JobRecord | None:
        job = self._repository.next_queued()
        if job is None:
            return None

        running = self._repository.transition(job.job_id, JobStatus.RUNNING)
        try:
            response = self._service.handle(
                AgentRequest(
                    session_id=running.session_id,
                    run_id=running.run_id,
                    content=str(running.payload.get("content", "")),
                    cwd=running.payload.get("cwd"),
                )
            )
        except Exception as exc:
            return self._repository.transition(
                running.job_id,
                JobStatus.FAILED,
                error=type(exc).__name__,
            )

        if response.status == "waiting_confirmation":
            return self._repository.transition(
                running.job_id,
                JobStatus.WAITING_CONFIRMATION,
            )
        if response.ok:
            return self._repository.transition(
                running.job_id,
                JobStatus.SUCCEEDED,
            )
        return self._repository.transition(
            running.job_id,
            JobStatus.FAILED,
            error="agent_response_failed",
        )
