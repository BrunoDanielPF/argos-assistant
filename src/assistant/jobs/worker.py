from assistant.jobs.models import JobRecord, JobStatus
from assistant.jobs.repository import JobRepository
from assistant.notifications.local import Notification
from assistant.runtime.contracts import AgentRequest


class JobWorker:
    def __init__(
        self,
        repository: JobRepository,
        service,
        notifier=None,
    ) -> None:
        self._repository = repository
        self._service = service
        self._notifier = notifier

    def run_once(self) -> JobRecord | None:
        job = self._repository.next_queued()
        if job is None:
            return None

        running = self._repository.transition(job.job_id, JobStatus.RUNNING)
        if running.payload.get("type") == "reminder":
            self._notify_reminder(running)
            return self._repository.transition(
                running.job_id,
                JobStatus.SUCCEEDED,
            )
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

    def _notify_reminder(self, job: JobRecord) -> None:
        if self._notifier is None:
            return
        content = job.payload.get("content", "Lembrete do Argos")
        self._notifier.notify(
            Notification(
                title="Argos",
                message=str(content),
            )
        )
