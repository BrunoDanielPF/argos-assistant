from assistant.models import AuditEvent, ChatMessage, SessionContext, SessionSnapshot, Suggestion


class SessionMemory:
    def __init__(self) -> None:
        self._history: list[ChatMessage] = []
        self._audit: list[AuditEvent] = []
        self._suggestions: list[Suggestion] = []
        self._context = SessionContext()

    @classmethod
    def from_snapshot(cls, snapshot: dict) -> "SessionMemory":
        validated = SessionSnapshot.model_validate(snapshot)
        memory = cls()
        memory._history = [
            message.model_copy(deep=True) for message in validated.history
        ]
        memory._audit = [
            event.model_copy(deep=True) for event in validated.audit
        ]
        memory._suggestions = [
            suggestion.model_copy(deep=True)
            for suggestion in validated.suggestions
        ]
        memory._context = validated.context.model_copy(deep=True)
        return memory

    def add_user_message(self, content: str) -> None:
        self._history.append(ChatMessage(role="user", content=content))

    def add_assistant_message(self, content: str) -> None:
        self._history.append(ChatMessage(role="assistant", content=content))

    def add_audit_event(self, event: AuditEvent) -> None:
        self._audit.append(event.model_copy(deep=True))

    def set_suggestions(self, suggestions: list[Suggestion]) -> None:
        self._suggestions = [suggestion.model_copy(deep=True) for suggestion in suggestions]

    def set_context(
        self,
        session_id: str | None = None,
        current_cwd: str | None = None,
        default_search_root: str | None = None,
        user_home: str | None = None,
    ) -> None:
        if session_id is not None:
            self._context.session_id = session_id
        if current_cwd is not None:
            self._context.current_cwd = current_cwd
        if default_search_root is not None:
            self._context.default_search_root = default_search_root
        if user_home is not None:
            self._context.user_home = user_home

    def set_last_search_results(self, results: list[str]) -> None:
        self._context.last_search_results = list(results)

    def set_pending_clarification(self, pending: dict) -> None:
        self._context.pending_clarification = dict(pending)
        action = pending.get("action")
        capability = action.get("capability") if isinstance(action, dict) else None
        field = pending.get("field")
        if isinstance(capability, str) and isinstance(field, str):
            self._context.active_task = {
                "capability": capability,
                "pending_field": field,
            }

    def clear_pending_clarification(self) -> None:
        self._context.pending_clarification = None
        self._context.active_task = None

    def snapshot(self) -> dict:
        return SessionSnapshot(
            history=self._history,
            audit=self._audit,
            suggestions=self._suggestions,
            context=self._context.model_copy(deep=True),
        ).model_dump()
