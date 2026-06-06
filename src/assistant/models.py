from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class Suggestion(BaseModel):
    text: str


class AuditEvent(BaseModel):
    kind: str
    message: str


class SessionContext(BaseModel):
    current_cwd: str | None = None
    default_search_root: str | None = None
    user_home: str | None = None
    last_search_results: list[str] = Field(default_factory=list)
    pending_clarification: dict | None = None


class SessionSnapshot(BaseModel):
    history: list[ChatMessage] = Field(default_factory=list)
    audit: list[AuditEvent] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    context: SessionContext = Field(default_factory=SessionContext)
