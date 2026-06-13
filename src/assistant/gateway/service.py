from threading import Lock, RLock
from uuid import uuid4

from assistant.capabilities.provisioning import CapabilityProvisioningProposal
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
        self._capability_graph = None
        if hasattr(runtime_factory, "build_capability_graph"):
            self._capability_graph = runtime_factory.build_capability_graph(
                reload_session=self._reload_session_runtime,
                execute_action=self._execute_workflow_action,
                audit=self._write_workflow_event,
            )

    def handle(self, request: AgentRequest) -> AgentResponse:
        if (
            self._capability_graph is not None
            and hasattr(self._capability_graph, "cleanup_expired")
        ):
            self._capability_graph.cleanup_expired()
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
            if self._is_capability_draft_proposal(result):
                proposal = CapabilityProvisioningProposal.model_validate(
                    result["confirmation"]["arguments"]
                )
                workflow_result = self._capability_graph.start_from_proposal(
                    session_id=request.session_id,
                    run_id=request.run_id,
                    proposal=proposal,
                )
                self._repository.save(
                    request.session_id,
                    agent.memory.snapshot(),
                )
                return self._workflow_response(
                    request.session_id,
                    request.run_id,
                    workflow_result,
                )
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
                error_code=result.get("error_code"),
            )

    def resolve_capability_tool_decision(
        self,
        workflow_id: str,
        decision: str,
    ) -> AgentResponse:
        if self._capability_graph is None:
            raise ValueError("Capability workflow is not configured")
        result = self._capability_graph.decide_tool(
            workflow_id,
            decision,
        )
        return self._workflow_response(
            self._workflow_session_id(workflow_id),
            self._workflow_run_id(workflow_id),
            result,
        )

    def resolve_capability_retry_decision(
        self,
        workflow_id: str,
        decision: str,
    ) -> AgentResponse:
        if self._capability_graph is None:
            raise ValueError("Capability workflow is not configured")
        result = self._capability_graph.decide_retry(
            workflow_id,
            decision,
        )
        return self._workflow_response(
            self._workflow_session_id(workflow_id),
            self._workflow_run_id(workflow_id),
            result,
        )

    def list_capability_workflows(
        self,
        session_id: str | None = None,
    ) -> list[dict]:
        if self._capability_graph is None:
            return []
        return self._capability_graph.list_pending(session_id)

    def cancel_capability_workflow(
        self,
        workflow_id: str,
    ) -> AgentResponse:
        if self._capability_graph is None:
            raise ValueError("Capability workflow is not configured")
        result = self._capability_graph.cancel(workflow_id)
        return self._workflow_response(
            self._workflow_session_id(workflow_id),
            self._workflow_run_id(workflow_id),
            result,
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
            if result.get("status") == "registry_reload_required":
                reload_payload = result["reload"]
                self._agents.pop(session_id, None)
                agent = self._get_or_create_agent_for_session(session_id)
                agent.record_registry_reload(reload_payload)
                result = agent.prepare_provisioned_retry(reload_payload)
                self._repository.save(
                    session_id,
                    agent.memory.snapshot(),
                )
                if result.get("status") != "waiting_confirmation":
                    self._write_event(
                        "registry_reload_failed",
                        request,
                        {
                            "tool_name": reload_payload["tool_name"],
                            "tool_version": reload_payload["tool_version"],
                            "error_code": result.get("error_code"),
                        },
                    )
                    return AgentResponse(
                        session_id=session_id,
                        run_id=pending["run_id"],
                        ok=result["ok"],
                        status="completed",
                        message=result["message"],
                        suggestions=result.get("suggestions", []),
                        error_code=result.get("error_code"),
                    )
                confirmation = self._persist_confirmation(
                    request,
                    result,
                )
                self._write_event(
                    "registry_reloaded",
                    request,
                    {
                        "tool_name": reload_payload["tool_name"],
                        "tool_version": reload_payload["tool_version"],
                    },
                )
                self._write_event(
                    "confirmation_required",
                    request,
                    {
                        "capability": confirmation.capability,
                        "policy": "confirm",
                        "reason": "provisioned_retry",
                    },
                )
                return AgentResponse(
                    session_id=session_id,
                    run_id=pending["run_id"],
                    ok=result["ok"],
                    status="waiting_confirmation",
                    message=result["message"],
                    suggestions=result.get("suggestions", []),
                    confirmation=confirmation,
                    error_code=result.get("error_code"),
                )
            if result.get("status") == "waiting_confirmation":
                confirmation = self._persist_confirmation(
                    request,
                    result,
                )
                self._write_event(
                    "confirmation_required",
                    request,
                    {
                        "capability": confirmation.capability,
                        "policy": "confirm",
                    },
                )
                return AgentResponse(
                    session_id=session_id,
                    run_id=pending["run_id"],
                    ok=result["ok"],
                    status="waiting_confirmation",
                    message=result["message"],
                    suggestions=result.get("suggestions", []),
                    confirmation=confirmation,
                    error_code=result.get("error_code"),
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
                error_code=result.get("error_code"),
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

    def _reload_session_runtime(self, session_id: str) -> None:
        self._agents.pop(session_id, None)
        self._get_or_create_agent_for_session(session_id)

    def _execute_workflow_action(
        self,
        session_id: str,
        action: dict,
    ) -> dict:
        agent = self._get_or_create_agent_for_session(session_id)
        result = agent.execute_confirmed_action(
            str(action["capability"]),
            dict(action.get("arguments") or {}),
            approved=True,
        )
        self._repository.save(session_id, agent.memory.snapshot())
        return result

    def _write_workflow_event(self, event: str, details: dict) -> None:
        if self._event_log is None:
            return
        self._event_log.write(
            event,
            str(details.get("session_id", "capability-workflow")),
            str(details.get("run_id", details.get("workflow_id", "unknown"))),
            details,
        )

    def _is_capability_draft_proposal(self, result: dict) -> bool:
        if self._capability_graph is None:
            return False
        confirmation = result.get("confirmation")
        return (
            result.get("error_code") == "capability_gap"
            and isinstance(confirmation, dict)
            and confirmation.get("capability") == "tool.provision_draft"
            and isinstance(confirmation.get("arguments"), dict)
        )

    def _workflow_session_id(self, workflow_id: str) -> str:
        repository = getattr(self._capability_graph, "_repository", None)
        record = repository.load(workflow_id) if repository is not None else None
        return record.session_id if record is not None else "default"

    def _workflow_run_id(self, workflow_id: str) -> str:
        repository = getattr(self._capability_graph, "_repository", None)
        record = repository.load(workflow_id) if repository is not None else None
        return record.run_id if record is not None else workflow_id

    @staticmethod
    def _workflow_response(
        session_id: str,
        run_id: str,
        result: dict,
    ) -> AgentResponse:
        workflow_status = result["status"]
        status = {
            "WAITING_TOOL_APPROVAL": "pending_approval",
            "WAITING_RETRY_CONFIRMATION": "pending_confirmation",
            "ACTION_EXECUTED": "success",
            "ACTION_FAILED": "error",
        }.get(workflow_status, "success_partial")
        return AgentResponse(
            session_id=session_id,
            run_id=run_id,
            ok=bool(result["ok"]),
            status=status,
            result=result.get("result"),
            workflow_id=result.get("workflow_id"),
            workflow_status=workflow_status,
            message=result["message"],
            suggestions=result.get("suggestions", []),
            approval=result.get("approval"),
            execution_result=result.get("execution_result"),
            error_code=result.get("error_code"),
        )

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
            arguments_summary=self._summarize_arguments(
                capability,
                arguments,
            ),
            permissions=payload.get(
                "permissions",
                self._describe_permissions(capability, arguments),
            ),
            question=(
                "Criar a tool local em draft para revisao?"
                if capability == "tool.provision_draft"
                else (
                    "Aprovar, instalar e habilitar esta tool local?"
                    if capability == "tool.approve_install_enable"
                    else f"Autorizar a execucao de {capability}?"
                )
            ),
            dry_run=payload.get("dry_run"),
        )

    @staticmethod
    def _summarize_arguments(
        capability: str,
        arguments: dict,
    ) -> dict:
        if capability == "tool.provision_draft":
            definition = arguments.get("definition")
            definition = (
                definition if isinstance(definition, dict) else {}
            )
            return {
                "requested_capability": arguments.get(
                    "requested_capability"
                ),
                "tool_name": definition.get("name"),
                "tool_version": definition.get("version"),
            }
        if capability == "tool.approve_install_enable":
            definition = arguments.get("definition")
            definition = (
                definition if isinstance(definition, dict) else {}
            )
            return {
                "tool_name": definition.get("name"),
                "tool_version": definition.get("version"),
                "draft_path": arguments.get("draft_path"),
            }
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
        if capability == "tool.provision_draft":
            return ["create:local_tool_draft", "execute:none"]
        if capability == "tool.approve_install_enable":
            return [
                "approve:local_tool",
                "install:local_tool",
                "enable:local_tool",
                "execute:none",
            ]
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
