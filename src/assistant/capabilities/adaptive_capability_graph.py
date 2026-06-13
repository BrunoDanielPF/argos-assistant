from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from assistant.capabilities.provisioning import (
    CapabilityProvisioningProposal,
    CapabilityProvisioningService,
    EnabledProvisionedTool,
)
from assistant.capabilities.workflow_repository import (
    CapabilityWorkflowRecord,
    CapabilityWorkflowRepository,
    PendingWorkflowLimit,
)
from assistant.workflows.redaction import redact_sensitive
from assistant.workflows.redaction import REDACTED


ToolDecision = Literal[
    "approve_enable_only",
    "approve_enable_and_run_once",
    "reject",
    "cancel",
]
RetryDecision = Literal["confirm", "reject", "cancel"]


class CapabilityGraphState(TypedDict, total=False):
    workflow_id: str
    proposal: dict
    session_id: str
    run_id: str
    original_action: dict
    platform_context: dict
    draft_path: str
    status: str
    tool_decision: str
    retry_decision: str
    enabled: dict
    execution_result: dict
    run_once_downgrade_reason: str
    dry_run: dict


class RunOnceEligibilityEvaluator:
    _blocked_capability_markers = (
        "shell",
        "environment",
        "env.",
        "system",
        "delete",
        "destroy",
        "remove",
        "write",
        "move",
    )
    _secret_keys = (
        "password",
        "secret",
        "token",
        "api_key",
        "credential",
    )

    def evaluate(
        self,
        *,
        enabled: EnabledProvisionedTool,
        original_action: dict,
        policy: str,
        retry_status: str,
        dry_run: dict,
    ) -> tuple[bool, str | None]:
        permissions = enabled.permissions
        if permissions.filesystem.write:
            return False, "filesystem_write"
        if permissions.network.enabled:
            return False, "network_enabled"
        if permissions.subprocess.executables:
            return False, "subprocess_enabled"
        if policy != "allow":
            return False, f"policy_{policy}"
        capability = str(original_action.get("capability", "")).casefold()
        if any(marker in capability for marker in self._blocked_capability_markers):
            return False, "effectful_capability"
        if self._contains_secret(original_action.get("arguments", {})):
            return False, "secret_arguments"
        if retry_status != "pending":
            return False, f"retry_{retry_status}"
        if (
            not dry_run.get("can_execute")
            or dry_run.get("requires_confirmation")
            or dry_run.get("risk") != "low"
        ):
            return False, "dry_run_not_read_only"
        return True, None

    def _contains_secret(self, value: object) -> bool:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).casefold().replace("-", "_")
                if any(marker in normalized for marker in self._secret_keys):
                    return True
                if self._contains_secret(item):
                    return True
        elif isinstance(value, (list, tuple)):
            return any(self._contains_secret(item) for item in value)
        return False


class AdaptiveCapabilityGraph:
    def __init__(
        self,
        *,
        provisioning_service: CapabilityProvisioningService,
        repository: CapabilityWorkflowRepository,
        checkpointer,
        reload_session: Callable[[str], None],
        execute_action: Callable[[str, dict], dict],
        policy_decider: Callable[[str, dict, dict], str],
        audit: Callable[[str, dict], None] | None = None,
        ttl: timedelta = timedelta(hours=24),
        now_fn: Callable[[], datetime] | None = None,
        eligibility_evaluator: RunOnceEligibilityEvaluator | None = None,
        dry_run_builder: Callable[[str, dict, dict], dict] | None = None,
    ) -> None:
        self._provisioning_service = provisioning_service
        self._repository = repository
        self._reload_session = reload_session
        self._execute_action = execute_action
        self._policy_decider = policy_decider
        self._audit_fn = audit
        self._ttl = ttl
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._eligibility_evaluator = (
            eligibility_evaluator or RunOnceEligibilityEvaluator()
        )
        self._dry_run_builder = dry_run_builder
        self._ephemeral_arguments: dict[str, dict] = {}
        self._graph = self._build_graph().compile(checkpointer=checkpointer)

    def start(
        self,
        *,
        session_id: str,
        run_id: str,
        requested_capability: str,
        user_goal: str,
        arguments: dict,
        platform_context: dict,
        original_action: dict,
    ) -> dict:
        self._audit(
            "capability_gap_detected",
            {
                "session_id": session_id,
                "run_id": run_id,
                "requested_capability": requested_capability,
            },
        )
        proposal = self._provisioning_service.propose(
            requested_capability=requested_capability,
            user_goal=user_goal,
            arguments=arguments,
            platform_context=platform_context,
            original_action=original_action,
        )
        return self.start_from_proposal(
            session_id=session_id,
            run_id=run_id,
            proposal=proposal,
        )

    def start_from_proposal(
        self,
        *,
        session_id: str,
        run_id: str,
        proposal: CapabilityProvisioningProposal,
    ) -> dict:
        if not proposal.can_create or proposal.definition is None:
            return {
                "ok": False,
                "result": "capability_gap",
                "status": "CAPABILITY_GAP_BLOCKED",
                "message": (
                    "Ainda nao tenho essa capacidade. A proposta de tool "
                    f"foi bloqueada: {proposal.reason or 'sem fonte segura'}."
                ),
                "error_code": "capability_gap",
            }

        equivalent = self._repository.find_equivalent_pending(
            session_id,
            proposal.definition.name,
            proposal.definition.version,
            proposal.tool_definition_hash or "",
        )
        if equivalent is not None:
            return self._response_for_record(equivalent)
        try:
            self._repository.ensure_pending_capacity(session_id)
        except PendingWorkflowLimit:
            return {
                "ok": True,
                "result": "success_partial",
                "status": "PENDING_DRAFT_LIMIT_REACHED",
                "message": (
                    "A sessao ja atingiu o limite de drafts pendentes. "
                    "Revise ou cancele uma pendencia antes de criar outra."
                ),
                "error_code": None,
            }

        workflow_id = str(uuid4())
        original_arguments = proposal.original_action.get("arguments")
        if self._requires_ephemeral_arguments(proposal.original_action):
            self._ephemeral_arguments[workflow_id] = dict(
                original_arguments
                if isinstance(original_arguments, dict)
                else {}
            )
        safe_proposal = self._sanitize_proposal(proposal)
        config = self._config(workflow_id)
        self._graph.invoke(
            {
                "workflow_id": workflow_id,
                "proposal": safe_proposal,
                "session_id": session_id,
                "run_id": run_id,
                "original_action": safe_proposal["original_action"],
                "platform_context": redact_sensitive(
                    proposal.platform_context
                ),
                "status": "CAPABILITY_GAP_DETECTED",
            },
            config,
        )
        record = self._require_record(workflow_id)
        return self._response_for_record(record)

    def decide_tool(
        self,
        workflow_id: str,
        decision: ToolDecision,
    ) -> dict:
        record = self._require_record(workflow_id)
        if record.status != "WAITING_TOOL_APPROVAL":
            return self._response_for_record(record)
        self._graph.invoke(
            Command(resume=decision),
            self._config(workflow_id),
        )
        return self._response_for_record(self._require_record(workflow_id))

    def decide_retry(
        self,
        workflow_id: str,
        decision: RetryDecision,
    ) -> dict:
        record = self._require_record(workflow_id)
        if record.status != "WAITING_RETRY_CONFIRMATION":
            return self._response_for_record(record)
        self._graph.invoke(
            Command(resume=decision),
            self._config(workflow_id),
        )
        return self._response_for_record(self._require_record(workflow_id))

    def list_pending(self, session_id: str | None = None) -> list[dict]:
        return [
            self._response_for_record(record)
            for record in self._repository.list_pending(session_id)
        ]

    def cancel(self, workflow_id: str) -> dict:
        record = self._require_record(workflow_id)
        if record.status == "WAITING_TOOL_APPROVAL":
            return self.decide_tool(workflow_id, "cancel")
        if record.status == "WAITING_RETRY_CONFIRMATION":
            return self.decide_retry(workflow_id, "cancel")
        return self._response_for_record(record)

    def cleanup_expired(
        self,
        *,
        now: datetime | None = None,
    ) -> list[str]:
        expired_ids = []
        for record in self._repository.list_expired(now=now):
            if record.status == "WAITING_TOOL_APPROVAL" and record.draft_path:
                proposal = CapabilityProvisioningProposal.model_validate(
                    record.proposal
                )
                self._provisioning_service.expire_draft(
                    proposal,
                    record.draft_path,
                )
            transitioned = self._repository.transition(
                record.workflow_id,
                expected=record.status,
                target="WORKFLOW_EXPIRED",
            )
            if transitioned is not None:
                expired_ids.append(record.workflow_id)
                self._audit(
                    "capability_workflow_expired",
                    {"workflow_id": record.workflow_id},
                )
        return expired_ids

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(CapabilityGraphState)
        graph.add_node("create_draft", self._create_draft)
        graph.add_node("wait_tool_approval", self._wait_tool_approval)
        graph.add_node("tool_rejected", self._tool_rejected)
        graph.add_node("tool_cancelled", self._tool_cancelled)
        graph.add_node("enable_tool", self._enable_tool)
        graph.add_node("reload_runtime", self._reload_runtime)
        graph.add_node("wait_retry", self._wait_retry)
        graph.add_node("retry_rejected", self._retry_rejected)
        graph.add_node("retry_cancelled", self._retry_cancelled)
        graph.add_node("execute_action", self._execute_original_action)
        graph.add_edge(START, "create_draft")
        graph.add_edge("create_draft", "wait_tool_approval")
        graph.add_conditional_edges(
            "wait_tool_approval",
            lambda state: state["tool_decision"],
            {
                "approve_enable_only": "enable_tool",
                "approve_enable_and_run_once": "enable_tool",
                "reject": "tool_rejected",
                "cancel": "tool_cancelled",
            },
        )
        graph.add_edge("tool_rejected", END)
        graph.add_edge("tool_cancelled", END)
        graph.add_edge("enable_tool", "reload_runtime")
        graph.add_conditional_edges(
            "reload_runtime",
            self._route_after_reload,
            {
                "execute": "execute_action",
                "confirm": "wait_retry",
            },
        )
        graph.add_conditional_edges(
            "wait_retry",
            lambda state: state["retry_decision"],
            {
                "confirm": "execute_action",
                "reject": "retry_rejected",
                "cancel": "retry_cancelled",
            },
        )
        graph.add_edge("retry_rejected", END)
        graph.add_edge("retry_cancelled", END)
        graph.add_edge("execute_action", END)
        return graph

    def _create_draft(self, state: CapabilityGraphState) -> dict:
        proposal = CapabilityProvisioningProposal.model_validate(
            state["proposal"]
        )
        draft = self._provisioning_service.create_draft(proposal)
        now = self._now_fn()
        definition = proposal.definition
        assert definition is not None
        record = CapabilityWorkflowRecord(
            workflow_id=state["workflow_id"],
            proposal_id=proposal.proposal_id,
            session_id=state["session_id"],
            run_id=state["run_id"],
            requested_capability=proposal.requested_capability,
            tool_name=definition.name,
            tool_version=definition.version,
            tool_definition_hash=proposal.tool_definition_hash or "",
            proposal=redact_sensitive(state["proposal"]),
            original_action=redact_sensitive(state["original_action"]),
            draft_path=str(draft.path),
            status="WAITING_TOOL_APPROVAL",
            retry_status="pending",
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            expires_at=(now + self._ttl).isoformat(),
        )
        self._repository.create(record)
        self._audit(
            "tool_draft_created",
            {
                "workflow_id": record.workflow_id,
                "proposal_id": record.proposal_id,
                "tool_name": record.tool_name,
                "tool_version": record.tool_version,
                "draft_path": record.draft_path,
            },
        )
        self._audit(
            "tool_validation_result",
            {
                "workflow_id": record.workflow_id,
                "status": draft.state,
                "ok": draft.state == "validated",
            },
        )
        self._audit(
            "tool_approval_pending",
            {"workflow_id": record.workflow_id},
        )
        return {
            "draft_path": str(draft.path),
            "status": "WAITING_TOOL_APPROVAL",
        }

    def _wait_tool_approval(self, state: CapabilityGraphState) -> dict:
        proposal = CapabilityProvisioningProposal.model_validate(
            state["proposal"]
        )
        definition = proposal.definition
        assert definition is not None
        read_only = self._can_offer_run_once(
            definition.permissions,
            proposal.original_action,
        )
        options = ["approve_enable_only", "reject", "cancel"]
        if read_only:
            options.insert(0, "approve_enable_and_run_once")
        decision = interrupt(
            {
                "workflow_id": state["workflow_id"],
                "tool_name": definition.name,
                "version": definition.version,
                "draft_path": state["draft_path"],
                "permissions": definition.permissions.model_dump(
                    mode="json"
                ),
                "options": options,
                "question": (
                    "Aprovar a instalacao e habilitacao desta tool local?"
                ),
            }
        )
        return {"tool_decision": decision}

    def _tool_rejected(self, state: CapabilityGraphState) -> dict:
        self._repository.transition(
            state["workflow_id"],
            expected="WAITING_TOOL_APPROVAL",
            target="TOOL_REJECTED",
        )
        self._audit("tool_rejected", {"workflow_id": state["workflow_id"]})
        return {"status": "TOOL_REJECTED"}

    def _tool_cancelled(self, state: CapabilityGraphState) -> dict:
        self._repository.transition(
            state["workflow_id"],
            expected="WAITING_TOOL_APPROVAL",
            target="TOOL_APPROVAL_CANCELLED",
        )
        self._audit(
            "tool_approval_cancelled",
            {"workflow_id": state["workflow_id"]},
        )
        return {"status": "TOOL_APPROVAL_CANCELLED"}

    def _enable_tool(self, state: CapabilityGraphState) -> dict:
        proposal = CapabilityProvisioningProposal.model_validate(
            state["proposal"]
        )
        definition = proposal.definition
        assert definition is not None
        tool_key = f"{definition.name}@{definition.version}"
        if not self._repository.acquire_tool_lease(
            tool_key,
            state["workflow_id"],
            expires_at=self._now_fn() + timedelta(minutes=5),
        ):
            raise RuntimeError(f"tool enablement is already in progress: {tool_key}")
        try:
            enabled = self._provisioning_service.approve_install_enable(
                proposal=proposal,
                draft_path=state["draft_path"],
            )
        finally:
            self._repository.release_tool_lease(
                tool_key,
                state["workflow_id"],
            )
        self._repository.transition(
            state["workflow_id"],
            expected="WAITING_TOOL_APPROVAL",
            target="TOOL_ENABLED",
        )
        self._audit(
            "tool_approved",
            {"workflow_id": state["workflow_id"]},
        )
        self._audit(
            "tool_enabled",
            {
                "workflow_id": state["workflow_id"],
                "tool_name": enabled.tool_name,
                "tool_version": enabled.tool_version,
            },
        )
        return {
            "enabled": enabled.model_dump(mode="json"),
            "status": "TOOL_ENABLED",
        }

    def _reload_runtime(self, state: CapabilityGraphState) -> dict:
        self._reload_session(state["session_id"])
        self._repository.transition(
            state["workflow_id"],
            expected="TOOL_ENABLED",
            target="RUNTIME_RELOADED",
        )
        self._audit(
            "session_registry_reloaded",
            {
                "workflow_id": state["workflow_id"],
                "session_id": state["session_id"],
            },
        )
        enabled = EnabledProvisionedTool.model_validate(state["enabled"])
        action = self._provisioning_service.build_retry_action(enabled)
        dry_run = self._build_dry_run(
            enabled,
            action,
            dict(state.get("platform_context") or {}),
        )
        return {"status": "RUNTIME_RELOADED", "dry_run": dry_run}

    def _route_after_reload(self, state: CapabilityGraphState) -> str:
        if state["tool_decision"] != "approve_enable_and_run_once":
            return "confirm"
        enabled = EnabledProvisionedTool.model_validate(state["enabled"])
        action = state["original_action"]
        policy = self._policy_decider(
            str(action.get("capability", "")),
            dict(action.get("arguments") or {}),
            dict(state.get("platform_context") or {}),
        )
        record = self._require_record(state["workflow_id"])
        eligible, reason = self._eligibility_evaluator.evaluate(
            enabled=enabled,
            original_action=action,
            policy=policy,
            retry_status=record.retry_status,
            dry_run=state["dry_run"],
        )
        if eligible:
            return "execute"
        self._audit(
            "run_once_downgraded",
            {
                "workflow_id": state["workflow_id"],
                "reason": reason,
            },
        )
        return "confirm"

    def _wait_retry(self, state: CapabilityGraphState) -> dict:
        record = self._repository.transition(
            state["workflow_id"],
            expected="RUNTIME_RELOADED",
            target="WAITING_RETRY_CONFIRMATION",
            execution_result={"dry_run": state["dry_run"]},
        )
        if record is not None:
            self._audit(
                "retry_confirmation_pending",
                {"workflow_id": state["workflow_id"]},
            )
        decision = interrupt(
            {
                "workflow_id": state["workflow_id"],
                "original_action": redact_sensitive(
                    state["original_action"]
                ),
                "dry_run": state["dry_run"],
                "question": "Executar agora a acao original?",
                "options": ["confirm", "reject", "cancel"],
            }
        )
        return {
            "retry_decision": decision,
            "status": "WAITING_RETRY_CONFIRMATION",
        }

    def _retry_rejected(self, state: CapabilityGraphState) -> dict:
        self._repository.transition(
            state["workflow_id"],
            expected="WAITING_RETRY_CONFIRMATION",
            target="RETRY_REJECTED",
        )
        self._audit("retry_rejected", {"workflow_id": state["workflow_id"]})
        return {"status": "RETRY_REJECTED"}

    def _retry_cancelled(self, state: CapabilityGraphState) -> dict:
        self._repository.transition(
            state["workflow_id"],
            expected="WAITING_RETRY_CONFIRMATION",
            target="RETRY_CANCELLED",
        )
        self._audit("retry_cancelled", {"workflow_id": state["workflow_id"]})
        return {"status": "RETRY_CANCELLED"}

    def _execute_original_action(
        self,
        state: CapabilityGraphState,
    ) -> dict:
        workflow_id = state["workflow_id"]
        current = self._require_record(workflow_id)
        if not self._repository.claim_retry(workflow_id):
            record = self._require_record(workflow_id)
            return {
                "status": record.status,
                "execution_result": record.execution_result or {},
            }
        self._audit("retry_confirmed", {"workflow_id": workflow_id})
        enabled = EnabledProvisionedTool.model_validate(state["enabled"])
        action = self._provisioning_service.build_retry_action(enabled)
        ephemeral = self._ephemeral_arguments.get(workflow_id)
        if (
            enabled.tool_name == "local.windows.env_set_user"
            and ephemeral is not None
        ):
            action["arguments"] = {
                key: ephemeral[key]
                for key in ("name", "value")
                if key in ephemeral
            }
        if self._contains_redacted(action):
            result = {
                "ok": False,
                "message": (
                    "Os argumentos sensiveis nao estao mais disponiveis. "
                    "Informe-os novamente para executar."
                ),
                "error_code": "sensitive_arguments_unavailable",
            }
        else:
            result = self._execute_action(state["session_id"], action)
        retry_status = "executed" if result.get("ok") else "failed"
        self._repository.complete_retry(
            workflow_id,
            status=retry_status,
            result=redact_sensitive(result),
        )
        target = (
            "ACTION_EXECUTED"
            if retry_status == "executed"
            else "ACTION_FAILED"
        )
        self._repository.transition(
            workflow_id,
            expected=current.status,
            target=target,
            execution_result=redact_sensitive(result),
        )
        self._audit(
            "capability_action_executed",
            {
                "workflow_id": workflow_id,
                "ok": bool(result.get("ok")),
            },
        )
        self._ephemeral_arguments.pop(workflow_id, None)
        return {"status": target, "execution_result": result}

    def _response_for_record(
        self,
        record: CapabilityWorkflowRecord,
    ) -> dict:
        if record.status == "WAITING_TOOL_APPROVAL":
            proposal = CapabilityProvisioningProposal.model_validate(
                record.proposal
            )
            definition = proposal.definition
            assert definition is not None
            options = ["approve_enable_only", "reject", "cancel"]
            if self._can_offer_run_once(
                definition.permissions,
                proposal.original_action,
            ):
                options.insert(0, "approve_enable_and_run_once")
            return {
                "ok": True,
                "result": "pending_approval",
                "status": record.status,
                "workflow_id": record.workflow_id,
                "message": (
                    "Draft local validado e quarentenado. A instalacao e "
                    "habilitacao exigem sua aprovacao."
                ),
                "approval": {
                    "tool_name": record.tool_name,
                    "version": record.tool_version,
                    "draft_path": record.draft_path,
                    "permissions": definition.permissions.model_dump(
                        mode="json"
                    ),
                    "options": options,
                },
                "error_code": None,
            }
        if record.status == "WAITING_RETRY_CONFIRMATION":
            dry_run = (
                record.execution_result.get("dry_run")
                if isinstance(record.execution_result, dict)
                else None
            )
            return {
                "ok": True,
                "result": "pending_confirmation",
                "status": record.status,
                "workflow_id": record.workflow_id,
                "message": (
                    "Tool habilitada e registry da sessao recarregada. "
                    "Confirme separadamente a execucao da acao original."
                ),
                "approval": {"dry_run": dry_run},
                "error_code": None,
            }
        result = {
            "TOOL_REJECTED": "rejected",
            "TOOL_APPROVAL_CANCELLED": "cancelled",
            "RETRY_REJECTED": "rejected",
            "RETRY_CANCELLED": "cancelled",
            "ACTION_EXECUTED": "success",
            "ACTION_FAILED": "error",
        }.get(record.status, record.status.casefold())
        return {
            "ok": record.status != "ACTION_FAILED",
            "result": result,
            "status": record.status,
            "workflow_id": record.workflow_id,
            "message": record.status.replace("_", " ").title(),
            "execution_result": record.execution_result,
            "error_code": (
                "execution_failed"
                if record.status == "ACTION_FAILED"
                else None
            ),
        }

    def _require_record(self, workflow_id: str) -> CapabilityWorkflowRecord:
        record = self._repository.load(workflow_id)
        if record is None:
            raise ValueError(f"capability workflow not found: {workflow_id}")
        return record

    @staticmethod
    def _config(workflow_id: str) -> dict:
        return {"configurable": {"thread_id": workflow_id}}

    @staticmethod
    def _is_read_only(permissions) -> bool:
        return (
            not permissions.filesystem.write
            and not permissions.network.enabled
            and not permissions.subprocess.executables
        )

    @classmethod
    def _can_offer_run_once(cls, permissions, original_action: dict) -> bool:
        capability = str(original_action.get("capability", "")).casefold()
        if any(
            marker in capability
            for marker in (
                "shell",
                "environment",
                "env.",
                "system",
                "delete",
                "destroy",
                "remove",
                "write",
                "move",
            )
        ):
            return False
        return cls._is_read_only(permissions)

    def _audit(self, event: str, details: dict) -> None:
        if self._audit_fn is not None:
            self._audit_fn(event, redact_sensitive(details))

    def _build_dry_run(
        self,
        enabled: EnabledProvisionedTool,
        action: dict,
        context: dict,
    ) -> dict:
        if self._dry_run_builder is not None:
            return self._dry_run_builder(
                str(action["capability"]),
                dict(action.get("arguments") or {}),
                context,
            )
        permissions = enabled.permissions
        return {
            "action": action["capability"],
            "risk": "low" if self._is_read_only(permissions) else "medium",
            "requires_confirmation": not self._is_read_only(permissions),
            "can_execute": True,
            "permissions_required": (
                [f"read:{item}" for item in permissions.filesystem.read]
            ),
            "expected_result": "A acao seria executada uma unica vez.",
        }

    @staticmethod
    def _requires_ephemeral_arguments(action: dict) -> bool:
        capability = str(action.get("capability", "")).casefold()
        return any(
            marker in capability
            for marker in ("environment", "env.", "system_config")
        )

    @staticmethod
    def _sanitize_proposal(
        proposal: CapabilityProvisioningProposal,
    ) -> dict:
        payload = proposal.model_dump(mode="json")
        payload["user_goal"] = REDACTED
        payload["arguments"] = redact_sensitive(payload["arguments"])
        action = redact_sensitive(payload["original_action"])
        capability = str(action.get("capability", "")).casefold()
        if any(
            marker in capability
            for marker in ("shell", "environment", "env.", "system")
        ):
            for key in ("command", "content", "value"):
                if key in payload["arguments"]:
                    payload["arguments"][key] = REDACTED
        arguments = action.get("arguments")
        if isinstance(arguments, dict) and any(
            marker in capability
            for marker in ("shell", "environment", "env.", "system")
        ):
            for key in ("command", "content", "value"):
                if key in arguments:
                    arguments[key] = REDACTED
        payload["original_action"] = action
        return payload

    @classmethod
    def _contains_redacted(cls, value: object) -> bool:
        if value == REDACTED:
            return True
        if isinstance(value, dict):
            return any(cls._contains_redacted(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(cls._contains_redacted(item) for item in value)
        return False
