from threading import Lock, RLock
from uuid import uuid4

from assistant.memory.session import SessionMemory
from assistant.observability.events import EventLog
from assistant.observability.metrics import Timer
from assistant.runtime.contracts import (
    AgentRequest,
    AgentResponse,
    ConfirmationRequest,
)
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
            agent.memory.set_context(session_id=request.session_id)
            if request.cwd:
                agent.memory.set_context(
                    current_cwd=request.cwd,
                    default_search_root=request.cwd,
                )
            timer = Timer.start()
            try:
                result = agent.handle(request.content)
            except Exception as exc:
                self._write_event(
                    "request_failed",
                    request,
                    {
                        "duration_ms": timer.elapsed_ms(),
                        "error_type": "internal",
                        "exception_type": type(exc).__name__,
                    },
                )
                raise

            confirmation = None
            if result.get("status") == "waiting_confirmation":
                confirmation = self._persist_confirmation(request, result)

            self._repository.save(request.session_id, agent.memory.snapshot())
            self._write_event(
                (
                    "confirmation_required"
                    if confirmation is not None
                    else "request_finished"
                ),
                request,
                {
                    "duration_ms": timer.elapsed_ms(),
                    "ok": bool(result["ok"]),
                    **(
                        {
                            "capability": confirmation.capability,
                            "policy": "confirm",
                        }
                        if confirmation is not None
                        else {}
                    ),
                },
            )
            return AgentResponse(
                session_id=request.session_id,
                run_id=request.run_id,
                ok=result["ok"],
                status=result.get("status", "completed"),
                message=result["message"],
                suggestions=result.get("suggestions", []),
                confirmation=confirmation,
            )

    def resolve_confirmation(
        self,
        confirmation_id: str,
        approved: bool,
    ) -> AgentResponse:
        pending = self._repository.resolve_confirmation(
            confirmation_id,
            approved=approved,
        )
        if pending is None:
            raise ValueError("Confirmation not found or already resolved")

        session_id = pending["session_id"]
        lock = self._get_session_lock(session_id)
        with lock:
            agent = self._get_or_create_agent_for_session(session_id)
            result = agent.execute_confirmed_action(
                pending["capability"],
                pending["arguments"],
                approved=approved,
            )
            self._repository.save(session_id, agent.memory.snapshot())
            request = AgentRequest(
                session_id=session_id,
                run_id=pending["run_id"],
                content="confirmation decision",
            )
            self._write_event(
                "confirmation_resolved",
                request,
                {
                    "capability": pending["capability"],
                    "policy": "confirm",
                    "decision": "approved" if approved else "rejected",
                    "decision_source": "user",
                    "ok": bool(result["ok"]),
                },
            )
            return AgentResponse(
                session_id=session_id,
                run_id=pending["run_id"],
                ok=result["ok"],
                status="completed",
                message=result["message"],
                suggestions=result.get("suggestions", []),
            )

    def _get_session_lock(self, session_id: str) -> RLock:
        with self._cache_lock:
            return self._session_locks.setdefault(session_id, RLock())

    def _get_or_create_agent(self, request: AgentRequest):
        return self._get_or_create_agent_for_session(request.session_id)

    def _get_or_create_agent_for_session(self, session_id: str):
        agent = self._agents.get(session_id)
        if agent is not None:
            return agent

        snapshot = self._repository.load(session_id)
        memory = (
            SessionMemory.from_snapshot(snapshot)
            if snapshot is not None
            else SessionMemory()
        )
        agent = self._runtime_factory.build_agent(memory=memory)
        self._agents[session_id] = agent
        return agent

    def _persist_confirmation(
        self,
        request: AgentRequest,
        result: dict,
    ) -> ConfirmationRequest:
        payload = result["confirmation"]
        capability = payload["capability"]
        arguments = payload["arguments"]
        confirmation_id = str(uuid4())
        self._repository.save_confirmation(
            confirmation_id=confirmation_id,
            session_id=request.session_id,
            run_id=request.run_id,
            capability=capability,
            arguments=arguments,
        )
        return ConfirmationRequest(
            confirmation_id=confirmation_id,
            capability=capability,
            arguments_summary=self._summarize_arguments(arguments),
            permissions=self._describe_permissions(capability, arguments),
            question=f"Autorizar a execucao de {capability}?",
            dry_run=payload.get("dry_run"),
        )

    @staticmethod
    def _summarize_arguments(arguments: dict) -> dict:
        summary = {}
        for key, value in arguments.items():
            if key == "content" and isinstance(value, str):
                summary["content_length"] = len(value)
                continue
            if key.lower() in {"token", "password", "secret"}:
                summary[key] = "[redacted]"
                continue
            summary[key] = value
        return summary

    @staticmethod
    def _describe_permissions(
        capability: str,
        arguments: dict,
    ) -> list[str]:
        if capability in {"create_file", "write_file"}:
            return [f"write:{arguments.get('path', 'unknown')}"]
        if capability == "search_files":
            return [f"read:{arguments.get('root', '.')}"]
        if capability == "run_shell_command":
            return ["subprocess"]
        if capability == "type_text":
            return ["desktop_input"]
        return [f"execute:{capability}"]

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
