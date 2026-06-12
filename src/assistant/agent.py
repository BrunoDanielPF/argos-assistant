from collections.abc import Callable
import inspect
from pathlib import Path
import sys

from assistant.capabilities.registry import (
    CapabilityRegistry,
    build_default_registry,
)
from assistant.capabilities.provisioning import (
    CapabilityProvisioningProposal,
)
from assistant.execution.policy import decide_policy
from assistant.files.resolver import FileResolver
from assistant.files.path_resolver import PathResolver
from assistant.intent.pending_resolver import (
    HELP_RESPONSE,
    PendingClarificationResolver,
    PendingResolutionStatus,
)
from assistant.memory.models import MemoryRecord
from assistant.memory.session import SessionMemory
from assistant.models import AuditEvent
from assistant.recovery.models import RecoveryStrategy
from assistant.suggestions import build_suggestions
from assistant.workflows.policies import is_destructive_shell_command


class AssistantAgent:
    def __init__(
        self,
        planner,
        executor,
        memory: SessionMemory | None = None,
        memory_engine=None,
        long_term_memory=None,
        policy_decider: Callable[[str], str] | None = None,
        action_validator: Callable[[str, dict], str | None] | None = None,
        confirmer: Callable[[str, dict], bool] | None = None,
        file_resolver: FileResolver | None = None,
        pending_resolver: PendingClarificationResolver | None = None,
        recovery_engine=None,
        capability_registry: CapabilityRegistry | None = None,
        path_resolver: PathResolver | None = None,
        capability_provisioning_service=None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._memory = memory or SessionMemory()
        self._memory_engine = memory_engine
        self._long_term_memory = long_term_memory
        has_custom_policy = policy_decider is not None
        self._policy_decider = policy_decider or decide_policy
        self._action_validator = action_validator or (lambda capability, arguments: None)
        self._confirmer = confirmer
        self._file_resolver = file_resolver or FileResolver()
        self._pending_resolver = pending_resolver or PendingClarificationResolver()
        self._recovery_engine = recovery_engine
        self._capability_registry = (
            capability_registry
            if capability_registry is not None
            else (None if has_custom_policy else build_default_registry())
        )
        self._path_resolver = path_resolver or PathResolver()
        self._capability_provisioning_service = (
            capability_provisioning_service
        )

    @property
    def memory(self) -> SessionMemory:
        return self._memory

    def _build_response(
        self,
        ok: bool,
        message: str,
        capability_name: str,
        policy: str | None = None,
        decision: str | None = None,
        reason: str | None = None,
        error_code: str | None = None,
    ) -> dict:
        self._memory.add_assistant_message(message)
        self._memory.add_audit_event(
            AuditEvent(
                kind="action",
                message=message,
                capability=capability_name,
                policy=policy,
                decision=decision,
                reason=reason,
            )
        )
        suggestions = build_suggestions(capability_name, message)
        self._memory.set_suggestions(suggestions)
        response = {
            "ok": ok,
            "status": "completed",
            "message": message,
            "suggestions": [item.model_dump() for item in suggestions],
        }
        if error_code is not None:
            response["error_code"] = error_code
        return response

    def _build_confirmation_response(
        self,
        capability_name: str,
        arguments: dict,
    ) -> dict:
        message = (
            f"Preciso da sua confirmacao antes de executar "
            f"{capability_name}."
        )
        self._memory.add_assistant_message(message)
        self._memory.add_audit_event(
            AuditEvent(
                kind="confirmation",
                message=message,
                capability=capability_name,
                policy="confirm",
                decision="pending",
                reason="confirmation_required",
            )
        )
        suggestions = build_suggestions("answer", message)
        self._memory.set_suggestions(suggestions)
        confirmation = {
            "capability": capability_name,
            "arguments": dict(arguments),
        }
        if (
            self._recovery_engine is not None
            and hasattr(self._recovery_engine, "preview_action")
        ):
            dry_run = self._recovery_engine.preview_action(
                capability_name,
                arguments,
            )
            if not dry_run.can_execute:
                return self._build_response(
                    ok=False,
                    message=dry_run.expected_result,
                    capability_name=capability_name,
                    reason=dry_run.error_code,
                    error_code=dry_run.error_code or "policy_blocked",
                )
            confirmation["dry_run"] = dry_run.model_dump(mode="json")
        return {
            "ok": False,
            "status": "waiting_confirmation",
            "message": message,
            "suggestions": [item.model_dump() for item in suggestions],
            "confirmation": confirmation,
        }

    def _execute_action(
        self,
        capability_name: str,
        arguments: dict,
        policy: str | None = None,
    ):
        policy = policy or self._policy_decider(capability_name)

        if policy == "blocked":
            if self._recovery_engine is not None:
                outcome = self._recovery_engine.handle_failure(
                    source="action",
                    operation=capability_name,
                    message=f"Blocked capability: {capability_name}",
                    arguments=arguments,
                    error_code="policy_blocked",
                )
                return type(
                    "Result",
                    (),
                    {
                        "ok": False,
                        "message": outcome.plan.user_message,
                        "data": None,
                        "error_code": "policy_blocked",
                    },
                )()
            return type(
                "Result",
                (),
                {
                    "ok": False,
                    "message": f"Blocked capability: {capability_name}",
                    "data": None,
                },
            )()

        if policy == "confirm":
            if self._confirmer is None:
                return type(
                    "Result",
                    (),
                    {
                        "ok": False,
                        "message": "Confirmation required",
                        "data": None,
                        "confirmation_required": True,
                    },
                )()
            confirmed = self._confirmer(capability_name, arguments)
            if not confirmed:
                return type(
                    "Result",
                    (),
                    {"ok": False, "message": "Action cancelled by user", "data": None},
                )()

        return self._execute_with_recovery(capability_name, arguments)

    def _execute_with_recovery(
        self,
        capability_name: str,
        arguments: dict,
    ):
        result = self._call_executor(capability_name, arguments)
        if result.ok or self._recovery_engine is None:
            return result

        error_code = getattr(result, "error_code", None)
        source = "tool" if "." in capability_name else "action"
        outcome = self._recovery_engine.handle_failure(
            source=source,
            operation=capability_name,
            message=result.message,
            arguments=arguments,
            error_code=error_code,
            metadata={
                "retry_safe": bool(getattr(result, "retry_safe", False))
            },
        )
        if outcome.plan.strategy == RecoveryStrategy.RETRY_WITH_BACKOFF:
            retried = self._call_executor(capability_name, arguments)
            self._recovery_engine.record_attempt(
                outcome,
                attempt=1,
                succeeded=bool(retried.ok),
                message=retried.message,
            )
            if retried.ok:
                return retried
            final_outcome = self._recovery_engine.handle_failure(
                source=source,
                operation=capability_name,
                message=retried.message,
                arguments=arguments,
                error_code=getattr(retried, "error_code", None),
                metadata={
                    "retry_safe": bool(
                        getattr(retried, "retry_safe", False)
                    )
                },
                attempt=1,
            )
            return type(
                "Result",
                (),
                {
                    "ok": False,
                    "message": (
                        f"{retried.message}\n"
                        f"{final_outcome.plan.user_message}"
                    ),
                    "data": getattr(retried, "data", None),
                    "error_code": getattr(retried, "error_code", None),
                },
            )()
        return type(
            "Result",
            (),
            {
                "ok": False,
                "message": f"{result.message}\n{outcome.plan.user_message}",
                "data": getattr(result, "data", None),
                "error_code": error_code,
            },
        )()

    def _call_executor(self, capability_name: str, arguments: dict):
        try:
            return self._executor.execute(capability_name, arguments)
        except Exception as exc:
            return type(
                "Result",
                (),
                {
                    "ok": False,
                    "message": (
                        f"Execution failed for {capability_name}: {exc}"
                    ),
                    "data": None,
                    "error_code": "execution_failed",
                    "retry_safe": False,
                },
            )()

    def execute_confirmed_action(
        self,
        capability_name: str,
        arguments: dict,
        approved: bool,
    ) -> dict:
        if not approved:
            return self._build_response(
                ok=False,
                message="Acao rejeitada pelo usuario.",
                capability_name=capability_name,
                policy="confirm",
                decision="rejected",
                reason="user_rejected",
            )
        if capability_name == "tool.provision_draft":
            if self._capability_provisioning_service is None:
                return self._build_response(
                    ok=False,
                    message="Capability provisioning is not configured.",
                    capability_name=capability_name,
                    policy="confirm",
                    decision="approved",
                    reason="provisioning_unavailable",
                    error_code="capability_gap",
                )
            try:
                proposal = CapabilityProvisioningProposal.model_validate(
                    arguments
                )
                draft = self._capability_provisioning_service.create_draft(
                    proposal
                )
            except Exception as exc:
                return self._build_response(
                    ok=False,
                    message=f"Nao foi possivel criar o draft: {exc}",
                    capability_name=capability_name,
                    policy="confirm",
                    decision="approved",
                    reason="draft_generation_failed",
                    error_code="capability_gap",
                )
            return self._build_response(
                ok=True,
                message=(
                    f"Tool draft criada em {draft.path}. "
                    f"Status: {draft.state}. A tool permanece desabilitada."
                ),
                capability_name=capability_name,
                policy="confirm",
                decision="approved",
                reason="draft_created",
                error_code="capability_gap",
            )
        context = self._memory.snapshot().get("context", {})
        if self._capability_registry is not None:
            prepared, validation_response = self._prepare_registry_action(
                capability_name,
                arguments,
                context,
            )
            if validation_response is not None:
                return validation_response
            assert prepared is not None
            capability_name, arguments, policy = prepared
            if policy == "blocked":
                return self._build_response(
                    ok=False,
                    message=f"Blocked capability: {capability_name}",
                    capability_name=capability_name,
                    policy=policy,
                    reason="policy_blocked",
                    error_code="policy_blocked",
                )
        result = self._execute_with_recovery(capability_name, arguments)
        return self._build_response(
            ok=result.ok,
            message=self._recover_failure_message(
                capability_name,
                arguments,
                result.message,
            ),
            capability_name=capability_name,
            policy="confirm",
            decision="approved",
            reason="user_approved",
            error_code=getattr(result, "error_code", None),
        )

    def _recover_failure_message(self, capability_name: str, arguments: dict, message: str) -> str:
        if capability_name in {"open_file", "file.open"} and message.startswith("File not found:"):
            path = arguments.get("path")
            if isinstance(path, str) and path.strip():
                return (
                    f"{message}\n"
                    f"Posso criar esse arquivo em {path} se voce informar o conteudo."
                )
        return message

    def _build_clarification_response(self, question: str, pending: dict) -> dict:
        self._memory.set_pending_clarification(pending)
        self._memory.add_assistant_message(question)
        suggestions = build_suggestions("answer", question)
        self._memory.set_suggestions(suggestions)
        return {
            "ok": True,
            "message": question,
            "suggestions": [item.model_dump() for item in suggestions],
        }

    def _prepare_action(self, capability_name: str, arguments: dict, context: dict) -> tuple[dict | None, dict | None]:
        if capability_name != "write_file":
            return arguments, None

        path = arguments.get("path")
        if not isinstance(path, str) or not path.strip():
            return arguments, None

        roots = []
        for key in ("current_cwd", "user_home", "default_search_root"):
            root = context.get(key)
            if isinstance(root, str) and root.strip() and root not in roots:
                roots.append(root)
        resolution = self._file_resolver.resolve(path, roots)
        if resolution.status == "resolved":
            resolved_arguments = dict(arguments)
            resolved_arguments["path"] = resolution.matches[0]
            return resolved_arguments, None

        if resolution.status == "ambiguous":
            if self._recovery_engine is not None:
                self._recovery_engine.handle_failure(
                    source="context",
                    operation=capability_name,
                    message=f"Ambiguous file context: {path}",
                    arguments=arguments,
                    error_code="context_ambiguity",
                    metadata={"match_count": len(resolution.matches)},
                )
            options = [
                {"id": match, "label": match}
                for match in resolution.matches
            ]
            options.append({"id": "cancel", "label": "cancelar"})
            pending = {
                "field": "path",
                "question": f"Encontrei mais de um arquivo parecido com '{path}'. Qual devo usar?",
                "action": {
                    "capability": capability_name,
                    "arguments": dict(arguments),
                },
                "options": options,
            }
        else:
            pending = {
                "field": "path",
                "question": (
                    f"Nao encontrei um arquivo parecido com '{path}'. "
                    "Informe o caminho completo do arquivo ou cancele."
                ),
                "action": {
                    "capability": capability_name,
                    "arguments": dict(arguments),
                },
                "options": [{"id": "cancel", "label": "cancelar"}],
                "accept_free_text": True,
            }

        question_lines = [pending["question"]]
        if resolution.status == "ambiguous":
            for index, option in enumerate(pending["options"], start=1):
                question_lines.append(f"{index}. {option['label']}")
        question_lines.append("Voce pode responder com o numero ou com suas proprias palavras.")
        response = self._build_clarification_response("\n".join(question_lines), pending)
        return None, response

    def _validate_action_response(
        self,
        capability_name: str,
        arguments: dict,
    ) -> dict | None:
        validation_message = self._action_validator(capability_name, arguments)
        if validation_message is None:
            return None
        return self._build_response(
            ok=False,
            message=validation_message,
            capability_name=capability_name,
            reason="invalid_arguments",
            error_code="invalid_schema",
        )

    def _prepare_registry_action(
        self,
        capability_name: str,
        arguments: dict,
        context: dict,
    ) -> tuple[tuple[str, dict, str] | None, dict | None]:
        assert self._capability_registry is not None
        normalized_input = dict(arguments)
        if "write_mode" in normalized_input and "mode" not in normalized_input:
            normalized_input["mode"] = normalized_input.pop("write_mode")
        if normalized_input.get("mode") == "replace":
            normalized_input["mode"] = "overwrite"

        validation = self._capability_registry.validate(
            capability_name,
            normalized_input,
        )
        if not validation.ok:
            return None, self._build_response(
                ok=False,
                message=validation.message or "Invalid action.",
                capability_name=capability_name,
                reason=validation.error_code,
                error_code=validation.error_code,
            )

        assert validation.capability is not None
        assert validation.arguments is not None
        canonical = validation.capability.name
        resolved_arguments = dict(validation.arguments)
        try:
            if canonical == "file.write":
                raw_path = resolved_arguments["path"]
                roots = [
                    context[key]
                    for key in (
                        "current_cwd",
                        "default_search_root",
                        "user_home",
                    )
                    if isinstance(context.get(key), str)
                    and context[key].strip()
                ]
                resolution = self._file_resolver.resolve(raw_path, roots)
                if resolution.status == "resolved":
                    resolved_arguments["path"] = resolution.matches[0]
                elif resolution.status == "ambiguous":
                    if self._recovery_engine is not None:
                        self._recovery_engine.handle_failure(
                            source="context",
                            operation=canonical,
                            message=f"Ambiguous file context: {raw_path}",
                            arguments=resolved_arguments,
                            error_code="context_ambiguity",
                            metadata={"match_count": len(resolution.matches)},
                        )
                    pending = {
                        "field": "path",
                        "question": (
                            f"Encontrei mais de um arquivo parecido com "
                            f"'{raw_path}'. Qual devo usar?"
                        ),
                        "action": {
                            "capability": canonical,
                            "arguments": resolved_arguments,
                        },
                        "options": [
                            {"id": match, "label": match}
                            for match in resolution.matches
                        ]
                        + [{"id": "cancel", "label": "cancelar"}],
                    }
                    question = self._format_pending_question(pending)
                    return None, self._build_clarification_response(
                        question,
                        pending,
                    )
                else:
                    resolved_arguments["path"] = str(
                        self._path_resolver.resolve(raw_path, context)
                    )
            elif canonical.startswith("file.") and canonical != "file.move_many":
                resolved_arguments["path"] = str(
                    self._path_resolver.resolve(
                        resolved_arguments["path"],
                        context,
                    )
                )
            elif canonical == "files.search":
                resolved_arguments["root"] = str(
                    self._path_resolver.resolve(
                        resolved_arguments["root"],
                        context,
                    )
                )
            elif canonical == "file.move_many":
                resolved_arguments["destination"] = str(
                    self._path_resolver.resolve(
                        resolved_arguments["destination"],
                        context,
                    )
                )
                if resolved_arguments.get("source_root"):
                    resolved_arguments["source_root"] = str(
                        self._path_resolver.resolve(
                            resolved_arguments["source_root"],
                            context,
                        )
                    )
                resolved_arguments["sources"] = [
                    str(self._path_resolver.resolve(source, context))
                    for source in resolved_arguments.get("sources", [])
                ]
        except (KeyError, TypeError, ValueError) as exc:
            return None, self._build_response(
                ok=False,
                message=f"Invalid schema for {canonical}: {exc}",
                capability_name=canonical,
                reason="invalid_schema",
                error_code="invalid_schema",
            )

        if canonical == "file.write" and resolved_arguments.get("mode") is None:
            target = Path(resolved_arguments["path"])
            try:
                is_empty_file = target.is_file() and target.stat().st_size == 0
            except OSError:
                is_empty_file = False
            if is_empty_file:
                resolved_arguments["mode"] = "overwrite"
            else:
                return None, self._build_response(
                    ok=False,
                    message=(
                        "Invalid schema for file.write: mode is required "
                        "and must be overwrite or append."
                    ),
                    capability_name=canonical,
                    reason="invalid_schema",
                    error_code="invalid_schema",
                )

        final_validation = self._capability_registry.validate(
            canonical,
            resolved_arguments,
        )
        if not final_validation.ok:
            return None, self._build_response(
                ok=False,
                message=final_validation.message or "Invalid action.",
                capability_name=canonical,
                reason=final_validation.error_code,
                error_code=final_validation.error_code,
            )
        assert final_validation.arguments is not None
        policy = decide_policy(
            canonical,
            final_validation.arguments,
            context,
            registry=self._capability_registry,
        )
        if policy == "blocked":
            message = f"Blocked capability: {canonical}"
            if self._recovery_engine is not None:
                outcome = self._recovery_engine.handle_failure(
                    source="action",
                    operation=canonical,
                    message=message,
                    arguments=final_validation.arguments,
                    error_code="policy_blocked",
                )
                message = outcome.plan.user_message
            return None, self._build_response(
                ok=False,
                message=message,
                capability_name=canonical,
                policy=policy,
                reason="policy_blocked",
                error_code="policy_blocked",
            )
        return (canonical, final_validation.arguments, policy), None

    def _build_capability_gap_response(
        self,
        *,
        user_goal: str,
        capability_name: str,
        arguments: dict,
        context: dict,
        original_action: dict,
    ) -> dict:
        assert self._capability_provisioning_service is not None
        platform_context = dict(context)
        platform_context["platform"] = sys.platform
        proposal = self._capability_provisioning_service.propose(
            requested_capability=capability_name,
            user_goal=user_goal,
            arguments=dict(arguments),
            platform_context=platform_context,
            original_action=dict(original_action),
        )
        if self._recovery_engine is not None:
            self._recovery_engine.handle_failure(
                source="planner",
                operation=capability_name,
                message=f"Capability gap: {capability_name}",
                arguments=arguments,
                error_code="capability_gap",
                metadata={
                    "proposal_status": proposal.status,
                    "proposal_id": proposal.proposal_id,
                },
            )
        if not proposal.can_create:
            return self._build_response(
                ok=False,
                message=(
                    "Ainda nao tenho essa capacidade e nao encontrei um "
                    "template local seguro para criar em draft."
                ),
                capability_name=capability_name,
                policy="blocked",
                decision="blocked",
                reason=proposal.reason,
                error_code="capability_gap",
            )

        message = (
            "Ainda não tenho essa capacidade. Posso criar uma tool local "
            "em draft para você revisar?"
        )
        self._memory.add_assistant_message(message)
        self._memory.add_audit_event(
            AuditEvent(
                kind="confirmation",
                message=message,
                capability="tool.provision_draft",
                policy="confirm",
                decision="pending",
                reason="capability_gap",
            )
        )
        suggestions = build_suggestions("answer", message)
        self._memory.set_suggestions(suggestions)
        return {
            "ok": False,
            "status": "waiting_confirmation",
            "message": message,
            "suggestions": [
                item.model_dump() for item in suggestions
            ],
            "error_code": "capability_gap",
            "confirmation": {
                "capability": "tool.provision_draft",
                "arguments": proposal.model_dump(),
            },
        }

    @staticmethod
    def _format_pending_question(pending: dict) -> str:
        lines = [str(pending["question"])]
        for index, option in enumerate(pending.get("options", []), start=1):
            lines.append(f"{index}. {option['label']}")
        lines.append(
            "Voce pode responder com o numero ou com suas proprias palavras."
        )
        return "\n".join(lines)

    @staticmethod
    def _inject_runtime_arguments(
        capability_name: str,
        arguments: dict,
        context: dict,
    ) -> dict:
        if capability_name != "schedule_reminder":
            return arguments
        session_id = context.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            return arguments
        return {**arguments, "session_id": session_id}

    @staticmethod
    def _normalize_file_creation(
        capability_name: str,
        arguments: dict,
    ) -> tuple[str, dict]:
        if capability_name != "write_file":
            return capability_name, arguments
        path = arguments.get("path")
        if not isinstance(path, str):
            return capability_name, arguments
        target = Path(path)
        if (
            target.is_absolute()
            and target.suffix
            and not target.exists()
            and arguments.get("write_mode") in {None, "replace"}
        ):
            normalized = dict(arguments)
            normalized.pop("write_mode", None)
            return "create_file", normalized
        return capability_name, arguments

    @staticmethod
    def _is_subject_reset_request(user_input: str) -> bool:
        normalized = user_input.strip().lower()
        reset_markers = (
            "esquece",
            "cancela isso",
            "cancelar isso",
            "muda de assunto",
            "troca de assunto",
            "deixa isso",
            "deixa pra la",
            "deixa para la",
            "agora quero",
            "na verdade",
        )
        return any(marker in normalized for marker in reset_markers)

    @staticmethod
    def _is_explicit_new_action_request(user_input: str) -> bool:
        normalized = user_input.strip().lower()
        action_markers = (
            "abra ",
            "abrir ",
            "open ",
            "crie ",
            "criar ",
            "apague ",
            "delete ",
            "execute ",
            "altere o path",
            "alterar o path",
            "adicione ao path",
            "configure ",
        )
        return any(normalized.startswith(marker) for marker in action_markers)

    def handle(self, user_input: str) -> dict:
        result = self._handle(user_input)
        if self._memory_engine is not None:
            try:
                context = self._memory.snapshot().get("context", {})
                self._memory_engine.observe(
                    user_input,
                    result.get("message", ""),
                    context,
                )
            except Exception:
                pass
        return result

    def _handle(self, user_input: str) -> dict:
        snapshot = self._memory.snapshot()
        previous_history = snapshot.get("history", [])
        snapshot_context = dict(snapshot.get("context") or {})
        pending_value = snapshot_context.get("pending_clarification")
        pending = pending_value if isinstance(pending_value, dict) else None
        pending_resolution = self._pending_resolver.resolve(user_input, pending)
        if pending_resolution.status == PendingResolutionStatus.HELP:
            self._memory.clear_pending_clarification()
            self._memory.add_user_message(user_input)
            return self._build_answer_response(HELP_RESPONSE)
        if pending_resolution.status == PendingResolutionStatus.CANCEL:
            self._memory.clear_pending_clarification()
            self._memory.add_user_message(user_input)
            return self._build_answer_response("Operação cancelada.")
        if pending_resolution.status == PendingResolutionStatus.NEW_INTENT:
            self._memory.clear_pending_clarification()
            snapshot_context["pending_clarification"] = None
        if pending_resolution.status == PendingResolutionStatus.UNRESOLVED:
            assert pending is not None
            self._memory.add_user_message(user_input)
            return self._build_clarification_response(
                pending_resolution.question or str(pending.get("question")),
                pending,
            )
        preplanned_action = None
        if pending_resolution.status == PendingResolutionStatus.RESOLVED:
            assert pending is not None
            assert pending_resolution.value is not None
            preplanned_action = self._pending_resolver.build_action(
                pending,
                pending_resolution.value,
            )
        subject_was_reset = self._is_subject_reset_request(user_input)
        explicit_new_action = (
            snapshot_context.get("pending_clarification") is not None
            and self._is_explicit_new_action_request(user_input)
        )
        if subject_was_reset or explicit_new_action:
            self._memory.clear_pending_clarification()
            snapshot_context["pending_clarification"] = None
            previous_history = []
        self._memory.add_user_message(user_input)
        try:
            if preplanned_action is not None:
                plan = preplanned_action
            else:
                planner_params = inspect.signature(self._planner.create_plan).parameters
                if "context" in planner_params:
                    context = dict(snapshot_context)
                    context["conversation_history"] = previous_history[-10:]
                    long_term_memories = []
                    if self._memory_engine is not None:
                        try:
                            structured_memories = self._memory_engine.retrieve(
                                user_input,
                                context,
                            )
                            long_term_memories = [
                                self._memory_record_to_context(memory)
                                for memory in structured_memories
                            ]
                        except Exception:
                            long_term_memories = []
                    if not long_term_memories and self._long_term_memory is not None:
                        long_term_memories = self._long_term_memory.search(user_input, max_results=5)
                    if long_term_memories:
                        context["long_term_memories"] = long_term_memories
                    plan = self._planner.create_plan(
                        user_input,
                        context=context,
                    )
                else:
                    plan = self._planner.create_plan(user_input)
        except Exception as exc:
            if self._recovery_engine is None:
                raise
            outcome = self._recovery_engine.handle_failure(
                source="planner",
                operation="create_plan",
                message=str(exc) or type(exc).__name__,
                exception=exc,
            )
            return self._build_response(
                ok=False,
                message=outcome.plan.user_message,
                capability_name="planner",
                reason=outcome.event.failure_type.value,
            )

        if plan["mode"] == "clarification":
            return self._build_clarification_response(
                question=plan["question"],
                pending=plan["pending"],
            )

        if snapshot_context.get("pending_clarification") is not None:
            self._memory.clear_pending_clarification()

        if plan["mode"] == "action":
            capability_name = plan["capability"]
            if (
                capability_name == "shell.run"
                and is_destructive_shell_command(
                    plan.get("arguments", {}).get("command")
                )
            ):
                return self._build_response(
                    ok=False,
                    message=(
                        "O comando shell foi bloqueado porque pode apagar "
                        "arquivos de forma recursiva ou destrutiva."
                    ),
                    capability_name=capability_name,
                    policy="blocked",
                    decision="blocked",
                    reason="policy_blocked",
                    error_code="policy_blocked",
                )
            if (
                self._capability_registry is not None
                and self._capability_registry.resolve(capability_name) is None
                and self._capability_provisioning_service is not None
            ):
                return self._build_capability_gap_response(
                    user_goal=user_input,
                    capability_name=capability_name,
                    arguments=plan["arguments"],
                    context=snapshot_context,
                    original_action=plan,
                )
            policy = None
            if self._capability_registry is not None:
                prepared, validation_response = self._prepare_registry_action(
                    capability_name,
                    plan["arguments"],
                    snapshot_context,
                )
                if validation_response is not None:
                    return validation_response
                assert prepared is not None
                capability_name, arguments, policy = prepared
            else:
                capability_name, planned_arguments = self._normalize_file_creation(
                    capability_name,
                    plan["arguments"],
                )
                arguments, clarification_response = self._prepare_action(
                    capability_name,
                    planned_arguments,
                    snapshot_context,
                )
                if clarification_response is not None:
                    return clarification_response
                assert arguments is not None
            arguments = self._inject_runtime_arguments(
                capability_name,
                arguments,
                snapshot_context,
            )
            validation_response = self._validate_action_response(
                capability_name,
                arguments,
            )
            if validation_response is not None:
                return validation_response
            result = self._execute_action(
                capability_name,
                arguments,
                policy=policy,
            )
            if getattr(result, "confirmation_required", False):
                return self._build_confirmation_response(
                    capability_name,
                    arguments,
                )
            if capability_name in {"search_files", "files.search"} and result.ok and result.data:
                matches = result.data.get("matches")
                if isinstance(matches, list):
                    self._memory.set_last_search_results(matches)
            return self._build_response(
                ok=result.ok,
                message=self._recover_failure_message(capability_name, arguments, result.message),
                capability_name=capability_name,
                error_code=getattr(result, "error_code", None),
            )

        if plan["mode"] == "plan":
            messages = []
            last_capability = "plan"
            for step in plan["steps"]:
                capability_name = step["capability"]
                policy = None
                if self._capability_registry is not None:
                    prepared, validation_response = self._prepare_registry_action(
                        capability_name,
                        step["arguments"],
                        snapshot_context,
                    )
                    if validation_response is not None:
                        return validation_response
                    assert prepared is not None
                    capability_name, arguments, policy = prepared
                else:
                    capability_name, planned_arguments = self._normalize_file_creation(
                        capability_name,
                        step["arguments"],
                    )
                    arguments, clarification_response = self._prepare_action(
                        capability_name,
                        planned_arguments,
                        snapshot_context,
                    )
                    if clarification_response is not None:
                        return clarification_response
                    assert arguments is not None
                arguments = self._inject_runtime_arguments(
                    capability_name,
                    arguments,
                    snapshot_context,
                )
                last_capability = capability_name
                validation_response = self._validate_action_response(
                    capability_name,
                    arguments,
                )
                if validation_response is not None:
                    return validation_response
                result = self._execute_action(
                    capability_name,
                    arguments,
                    policy=policy,
                )
                if getattr(result, "confirmation_required", False):
                    return self._build_confirmation_response(
                        capability_name,
                        arguments,
                    )
                messages.append(result.message)
                if not result.ok:
                    return self._build_response(
                        ok=False,
                        message=self._recover_failure_message(
                            capability_name,
                            arguments,
                            "\n".join(messages),
                        ),
                        capability_name=capability_name,
                        error_code=getattr(result, "error_code", None),
                    )
            return self._build_response(
                ok=True,
                message="\n".join(messages),
                capability_name=last_capability,
            )

        return self._build_answer_response(plan["content"])

    def _build_answer_response(self, answer: str) -> dict:
        self._memory.add_assistant_message(answer)
        suggestions = build_suggestions("answer", answer)
        self._memory.set_suggestions(suggestions)
        return {
            "ok": True,
            "status": "completed",
            "message": answer,
            "suggestions": [item.model_dump() for item in suggestions],
        }

    @staticmethod
    def _memory_record_to_context(memory) -> dict:
        if isinstance(memory, dict):
            return memory
        if isinstance(memory, MemoryRecord):
            return {
                "memory_id": memory.id,
                "memory_type": memory.type.value,
                "learning": memory.content,
                "context": memory.scope_value or memory.scope,
                "source": memory.source,
            }
        raise TypeError("Unsupported memory result")
