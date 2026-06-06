from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1)
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    cwd: str | None = None


class AgentResponse(StrictModel):
    session_id: str
    run_id: str
    ok: bool
    message: str
    suggestions: list[dict] = Field(default_factory=list)
