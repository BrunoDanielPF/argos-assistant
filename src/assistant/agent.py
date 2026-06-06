from collections.abc import Callable
import inspect

from assistant.execution.policy import decide_policy
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
        confirmer: Callable[[str, dict], bool] | None = None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._memory = memory or SessionMemory()
        self._long_term_memory = long_term_memory
        self._policy_decider = policy_decider or decide_policy
        self._confirmer = confirmer

    @property
    def memory(self) -> SessionMemory:
        return self._memory

    def _build_response(self, ok: bool, message: str, capability_name: str) -> dict:
        self._memory.add_assistant_message(message)
        self._memory.add_audit_event(AuditEvent(kind="action", message=message))
        suggestions = build_suggestions(capability_name, message)
        self._memory.set_suggestions(suggestions)
        return {
            "ok": ok,
            "message": message,
            "suggestions": [item.model_dump() for item in suggestions],
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
            confirmed = self._confirmer(capability_name, arguments) if self._confirmer else False
            if not confirmed:
                return type(
                    "Result",
                    (),
                    {"ok": False, "message": "Action cancelled by user", "data": None},
                )()

        return self._executor.execute(capability_name, arguments)

    def _recover_failure_message(self, capability_name: str, arguments: dict, message: str) -> str:
        if capability_name == "open_file" and message.startswith("File not found:"):
            path = arguments.get("path")
            if isinstance(path, str) and path.strip():
                return (
                    f"{message}\n"
                    f"Posso criar esse arquivo em {path} se voce informar o conteudo."
                )
        return message

    def handle(self, user_input: str) -> dict:
        snapshot = self._memory.snapshot()
        previous_history = snapshot.get("history", [])
        self._memory.add_user_message(user_input)
        planner_params = inspect.signature(self._planner.create_plan).parameters
        if "context" in planner_params:
            context = dict(snapshot.get("context") or {})
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

        if plan["mode"] == "action":
            capability_name = plan["capability"]
            arguments = plan["arguments"]
            result = self._execute_action(capability_name, arguments)
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
                arguments = step["arguments"]
                last_capability = capability_name
                result = self._execute_action(capability_name, arguments)
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
            "message": answer,
            "suggestions": [item.model_dump() for item in suggestions],
        }
