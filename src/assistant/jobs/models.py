from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class InvalidJobTransition(ValueError):
    pass


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_CONFIRMATION = "waiting_confirmation"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CANCELLING = "cancelling"


TERMINAL_STATUSES = {
    JobStatus.SUCCEEDED,
    JobStatus.CANCELLED,
}


VALID_TRANSITIONS = {
    JobStatus.QUEUED: {
        JobStatus.RUNNING,
        JobStatus.CANCELLED,
    },
    JobStatus.RUNNING: {
        JobStatus.WAITING_CONFIRMATION,
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELLING,
    },
    JobStatus.WAITING_CONFIRMATION: {
        JobStatus.RUNNING,
        JobStatus.CANCELLED,
        JobStatus.FAILED,
    },
    JobStatus.FAILED: {
        JobStatus.QUEUED,
        JobStatus.CANCELLED,
    },
    JobStatus.CANCELLING: {
        JobStatus.CANCELLED,
    },
    JobStatus.SUCCEEDED: set(),
    JobStatus.CANCELLED: set(),
}


class JobRecord(BaseModel):
    job_id: str
    session_id: str
    run_id: str
    status: JobStatus
    payload: dict = Field(default_factory=dict)
    scheduled_for: datetime | None = None
    created_at: datetime
    updated_at: datetime
    attempts: int = 0
    last_error: str | None = None


def ensure_valid_transition(current: JobStatus, target: JobStatus) -> None:
    if target not in VALID_TRANSITIONS[current]:
        raise InvalidJobTransition(
            f"Invalid job transition from {current.value} to {target.value}"
        )
