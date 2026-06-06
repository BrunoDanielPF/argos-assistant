from threading import Lock, RLock

from assistant.memory.session import SessionMemory
from assistant.observability.events import EventLog
from assistant.observability.metrics import Timer
from assistant.runtime.contracts import AgentRequest, AgentResponse
from assistant.sessions.repository import SessionRepository


class GatewayService:
    def __init__(
        self,
        runtime_factory,
        repository: SessionRepository,
        event_log: EventLog | None = None,
    ) -> None:
        self._runtime_factory = runtime_factory
        self._repository = repository
        self._event_log = event_log
        self._agents: dict[str, object] = {}
        self._session_locks: dict[str, RLock] = {}
        self._cache_lock = Lock()

    def handle(self, request: AgentRequest) -> AgentResponse:
        lock = self._get_session_lock(request.session_id)
        with lock:
            agent = self._get_or_create_agent(request)
            if request.cwd:
                agent.memory.set_context(
                    current_cwd=request.cwd,
                    default_search_root=request.cwd,
                )
            timer = Timer.start()
            try:
                result = agent.handle(request.content)
            except Exception:
                self._write_event(
                    "request_failed",
                    request,
                    {"duration_ms": timer.elapsed_ms(), "error_type": "internal"},
                )
                raise

            self._repository.save(request.session_id, agent.memory.snapshot())
            self._write_event(
                "request_finished",
                request,
                {"duration_ms": timer.elapsed_ms(), "ok": bool(result["ok"])},
            )
            return AgentResponse(
                session_id=request.session_id,
                run_id=request.run_id,
                ok=result["ok"],
                message=result["message"],
                suggestions=result.get("suggestions", []),
            )

    def _get_session_lock(self, session_id: str) -> RLock:
        with self._cache_lock:
            return self._session_locks.setdefault(session_id, RLock())

    def _get_or_create_agent(self, request: AgentRequest):
        agent = self._agents.get(request.session_id)
        if agent is not None:
            return agent

        snapshot = self._repository.load(request.session_id)
        memory = (
            SessionMemory.from_snapshot(snapshot)
            if snapshot is not None
            else SessionMemory()
        )
        agent = self._runtime_factory.build_agent(memory=memory)
        self._agents[request.session_id] = agent
        return agent

    def _write_event(
        self,
        kind: str,
        request: AgentRequest,
        details: dict,
    ) -> None:
        if self._event_log is None:
            return
        self._event_log.write(
            kind,
            request.session_id,
            request.run_id,
            details,
        )
