from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InvalidWorkflowTransition(ValueError):
    pass


class WorkflowStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    ENABLED = "enabled"
    DISABLED = "disabled"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class WorkflowRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class WorkflowRunStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


class WorkflowTriggerType(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    FILE_CREATED = "file_created"
    JOB_FAILED = "job_failed"


class WorkflowStrategy(StrEnum):
    SEQUENTIAL = "sequential"


class WorkflowTrigger(StrictModel):
    type: WorkflowTriggerType
    arguments: dict = Field(default_factory=dict)


class WorkflowPolicy(StrictModel):
    default_decision: PolicyDecision = PolicyDecision.BLOCKED
    actions: dict[str, PolicyDecision] = Field(default_factory=dict)


class WorkflowStep(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    uses: str = Field(min_length=1, max_length=200)
    with_args: dict = Field(default_factory=dict)
    if_condition: str | None = None
    requires_confirmation: bool = False
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    continue_on_error: bool = False


class WorkflowBudget(StrictModel):
    max_steps: int = Field(ge=1)
    max_runtime_seconds: int = Field(ge=1)
    max_model_calls: int = Field(ge=0)
    max_parallel_tasks: int = Field(ge=1)


class WorkflowHandlerResult(StrictModel):
    ok: bool = True
    output: dict = Field(default_factory=dict)
    error: str | None = None


class Workflow(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    schema_version: Literal["1.0"] = "1.0"
    status: WorkflowStatus = WorkflowStatus.DRAFT
    trigger: WorkflowTrigger
    strategy: WorkflowStrategy = WorkflowStrategy.SEQUENTIAL
    steps: list[WorkflowStep] = Field(min_length=1)
    policy: WorkflowPolicy
    budget: WorkflowBudget
    scope: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    enabled_at: datetime | None = None
    source_prompt: str | None = None
    metadata: dict = Field(default_factory=dict)


class WorkflowRun(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str
    status: WorkflowRunStatus = WorkflowRunStatus.PENDING
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    trigger_event: dict | None = None
    error: str | None = None
    audit_id: str | None = None


class WorkflowRunStep(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    step_id: str
    status: WorkflowRunStepStatus = WorkflowRunStepStatus.PENDING
    input_json: dict | None = None
    output_json: dict | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


WORKFLOW_TRANSITIONS = {
    WorkflowStatus.DRAFT: {
        WorkflowStatus.VALIDATED,
        WorkflowStatus.REJECTED,
        WorkflowStatus.ARCHIVED,
    },
    WorkflowStatus.VALIDATED: {
        WorkflowStatus.APPROVED,
        WorkflowStatus.REJECTED,
        WorkflowStatus.ARCHIVED,
    },
    WorkflowStatus.APPROVED: {
        WorkflowStatus.ENABLED,
        WorkflowStatus.REJECTED,
        WorkflowStatus.ARCHIVED,
    },
    WorkflowStatus.ENABLED: {
        WorkflowStatus.DISABLED,
        WorkflowStatus.ARCHIVED,
    },
    WorkflowStatus.DISABLED: {
        WorkflowStatus.ENABLED,
        WorkflowStatus.ARCHIVED,
    },
    WorkflowStatus.REJECTED: {WorkflowStatus.ARCHIVED},
    WorkflowStatus.ARCHIVED: set(),
}


def ensure_valid_workflow_transition(
    current: WorkflowStatus,
    target: WorkflowStatus,
) -> None:
    if target not in WORKFLOW_TRANSITIONS[current]:
        raise InvalidWorkflowTransition(
            f"Invalid workflow transition from {current.value} to {target.value}"
        )
