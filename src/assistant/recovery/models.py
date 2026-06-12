from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FailureType(StrEnum):
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    CAPABILITY_GAP = "capability_gap"
    INVALID_SCHEMA = "invalid_schema"
    WRONG_INTENT = "wrong_intent"
    NO_RESULTS = "no_results"
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"
    INVALID_ARGUMENTS = "invalid_arguments"
    PERMISSION_DENIED = "permission_denied"
    POLICY_BLOCKED = "policy_blocked"
    TOOL_ERROR = "tool_error"
    CONTEXT_AMBIGUITY = "context_ambiguity"
    UNKNOWN = "unknown"


class RecoveryStrategy(StrEnum):
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    EXPLAIN_POLICY_BLOCK = "explain_policy_block"
    SUGGEST_SAFE_ALTERNATIVE = "suggest_safe_alternative"
    REBUILD_CONTEXT = "rebuild_context"
    DRY_RUN_THEN_CONFIRM = "dry_run_then_confirm"
    FALLBACK_TO_PARTIAL_ANSWER = "fallback_to_partial_answer"


class RecoveryRisk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureEvent(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    source: str
    operation: str
    failure_type: FailureType
    message: str
    error_code: str | None = None
    exception_type: str | None = None
    metadata: dict = Field(default_factory=dict)
    attempt: int = Field(default=0, ge=0)


class RecoveryPlan(StrictModel):
    failure_type: FailureType
    strategy: RecoveryStrategy
    risk: RecoveryRisk
    requires_confirmation: bool
    user_message: str
    max_retries: int = Field(default=0, ge=0, le=1)


class RecoveryDecision(StrictModel):
    allowed: bool
    requires_confirmation: bool
    risk: RecoveryRisk
    reason: str


class DryRunPlan(StrictModel):
    action: str
    resources_affected: list[str] = Field(default_factory=list)
    risk: RecoveryRisk
    permissions_required: list[str] = Field(default_factory=list)
    requires_confirmation: bool
    expected_result: str
    can_execute: bool = True
    error_code: str | None = None


class RecoveryOutcome(StrictModel):
    event: FailureEvent
    plan: RecoveryPlan
    dry_run: DryRunPlan | None = None
    status: Literal["planned", "retried", "recovered", "blocked"] = "planned"


class RecoveryAttempt(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    failure_event_id: str
    strategy: RecoveryStrategy
    attempt: int = Field(ge=1, le=1)
    succeeded: bool
    message: str
