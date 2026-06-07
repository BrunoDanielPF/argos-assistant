from collections.abc import Callable
import inspect
from pathlib import Path

from assistant.execution.policy import decide_policy
from assistant.files.resolver import FileResolver
from assistant.memory.session import SessionMemory
from assistant.models import AuditEvent
from assistant.suggestions import build_suggestions


class AssistantAgent:
    def __init__(
        self,
        planner,
        executor,
        memory: SessionMemory | None = None,
        long_term_memory=None,
        policy_decider: Callable[[str], str] | None = None,
        action_validator: Callable[[str, dict], str | None] | None = None,
        confirmer: Callable[[str, dict], bool] | None = None,
        file_resolver: FileResolver | None = None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._memory = memory or SessionMemory()
        self._long_term_memory = long_term_memory
        self._policy_decider = policy_decider or decide_policy
        self._action_validator = action_validator or (lambda capability, arguments: None)
        self._confirmer = confirmer
        self._file_resolver = file_resolver or FileResolver()

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
        return {
            "ok": ok,
            "status": "completed",
            "message": message,
            "suggestions": [item.model_dump() for item in suggestions],
        }

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
        return {
            "ok": False,
            "status": "waiting_confirmation",
            "message": message,
            "suggestions": [item.model_dump() for item in suggestions],
            "confirmation": {
                "capability": capability_name,
                "arguments": dict(arguments),
            },
        }

    def _execute_action(self, capability_name: str, arguments: dict):
        policy = self._policy_decider(capability_name)

        if policy == "blocked":
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

        return self._executor.execute(capability_name, arguments)

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
        result = self._executor.execute(capability_name, arguments)
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
        )

    def _recover_failure_message(self, capability_name: str, arguments: dict, message: str) -> str:
        if capability_name == "open_file" and message.startswith("File not found:"):
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
            ok=True,
            message=validation_message,
            capability_name=capability_name,
            reason="invalid_arguments",
        )

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

    def handle(self, user_input: str) -> dict:
        snapshot = self._memory.snapshot()
        previous_history = snapshot.get("history", [])
        snapshot_context = dict(snapshot.get("context") or {})
        subject_was_reset = self._is_subject_reset_request(user_input)
        if subject_was_reset:
            self._memory.clear_pending_clarification()
            snapshot_context["pending_clarification"] = None
            previous_history = []
        self._memory.add_user_message(user_input)
        planner_params = inspect.signature(self._planner.create_plan).parameters
        if "context" in planner_params:
            context = dict(snapshot_context)
            context["conversation_history"] = previous_history[-10:]
            if self._long_term_memory is not None:
                long_term_memories = self._long_term_memory.search(user_input, max_results=5)
                if long_term_memories:
                    context["long_term_memories"] = long_term_memories
            plan = self._planner.create_plan(
                user_input,
                context=context,
            )
        else:
            plan = self._planner.create_plan(user_input)

        if plan["mode"] == "clarification":
            return self._build_clarification_response(
                question=plan["question"],
                pending=plan["pending"],
            )

        if snapshot_context.get("pending_clarification") is not None:
            self._memory.clear_pending_clarification()

        if plan["mode"] == "action":
            capability_name = plan["capability"]
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
            validation_response = self._validate_action_response(
                capability_name,
                arguments,
            )
            if validation_response is not None:
                return validation_response
            result = self._execute_action(capability_name, arguments)
            if getattr(result, "confirmation_required", False):
                return self._build_confirmation_response(
                    capability_name,
                    arguments,
                )
            if capability_name == "search_files" and result.ok and result.data:
                matches = result.data.get("matches")
                if isinstance(matches, list):
                    self._memory.set_last_search_results(matches)
            return self._build_response(
                ok=result.ok,
                message=self._recover_failure_message(capability_name, arguments, result.message),
                capability_name=capability_name,
            )

        if plan["mode"] == "plan":
            messages = []
            last_capability = "plan"
            for step in plan["steps"]:
                capability_name = step["capability"]
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
                last_capability = capability_name
                validation_response = self._validate_action_response(
                    capability_name,
                    arguments,
                )
                if validation_response is not None:
                    return validation_response
                result = self._execute_action(capability_name, arguments)
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
                    )
            return self._build_response(
                ok=True,
                message="\n".join(messages),
                capability_name=last_capability,
            )

        answer = plan["content"]
        self._memory.add_assistant_message(answer)
        suggestions = build_suggestions("answer", answer)
        self._memory.set_suggestions(suggestions)
        return {
            "ok": True,
            "status": "completed",
            "message": answer,
            "suggestions": [item.model_dump() for item in suggestions],
        }
