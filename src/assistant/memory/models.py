from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    USER_PREFERENCE = "user_preference"
    PROJECT_PREFERENCE = "project_preference"
    PROJECT_DECISION = "project_decision"
    PROJECT_FACT = "project_fact"
    TOOL_USAGE_PATTERN = "tool_usage_pattern"
    COMMAND_PATTERN = "command_pattern"
    CORRECTION = "correction"
    TEMPORARY_CONTEXT = "temporary_context"


class MemoryStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class MemoryDecision(str, Enum):
    AUTO_SAVE = "auto_save"
    CONFIRM = "confirm"
    BLOCK = "block"
    IGNORE = "ignore"


class MemoryCandidate(BaseModel):
    type: MemoryType
    content: str
    scope: str = "user"
    scope_value: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = "conversation"
    source_ref: str | None = None
    observed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class MemoryClassification(BaseModel):
    decision: MemoryDecision
    status: MemoryStatus | None = None
    reason: str


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: MemoryType
    status: MemoryStatus
    content: str
    scope: str
    scope_value: str | None = None
    importance: float
    confidence: float
    source: str
    source_ref: str | None = None
    observed_at: datetime
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class MemoryObservation(BaseModel):
    candidate: MemoryCandidate
    decision: MemoryDecision
    reason: str
    record: MemoryRecord | None = None

