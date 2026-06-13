from uuid import uuid4
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1)
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    cwd: str | None = None


class ConfirmationRequest(StrictModel):
    confirmation_id: str
    capability: str
    arguments_summary: dict = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    question: str
    dry_run: dict | None = None


class ConfirmationDecision(StrictModel):
    approved: bool


class CapabilityToolDecision(StrictModel):
    decision: Literal[
        "approve_enable_only",
        "approve_enable_and_run_once",
        "reject",
        "cancel",
    ]


class CapabilityRetryDecision(StrictModel):
    decision: Literal["confirm", "reject", "cancel"]


class AgentResponse(StrictModel):
    session_id: str
    run_id: str
    ok: bool
    status: Literal[
        "completed",
        "waiting_confirmation",
        "success",
        "success_partial",
        "pending_confirmation",
        "pending_approval",
        "error",
    ] = "completed"
    message: str
    suggestions: list[dict] = Field(default_factory=list)
    confirmation: ConfirmationRequest | None = None
    error_code: str | None = None
    result: str | None = None
    workflow_id: str | None = None
    workflow_status: str | None = None
    approval: dict | None = None
    execution_result: dict | None = None
