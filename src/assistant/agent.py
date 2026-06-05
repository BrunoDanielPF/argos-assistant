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
        policy_decider: Callable[[str], str] | None = None,
        confirmer: Callable[[str, dict], bool] | None = None,
    ) -> None:
        self._planner = planner
        self._executor = executor
        self._memory = memory or SessionMemory()
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

    def handle(self, user_input: str) -> dict:
        self._memory.add_user_message(user_input)
        planner_params = inspect.signature(self._planner.create_plan).parameters
        if "context" in planner_params:
            plan = self._planner.create_plan(
                user_input,
                context=self._memory.snapshot().get("context"),
            )
        else:
            plan = self._planner.create_plan(user_input)

        if plan["mode"] == "action":
            capability_name = plan["capability"]
            arguments = plan["arguments"]
            policy = self._policy_decider(capability_name)

            if policy == "blocked":
                return self._build_response(
                    ok=False,
                    message=f"Blocked capability: {capability_name}",
                    capability_name=capability_name,
                )

            if policy == "confirm":
                confirmed = self._confirmer(capability_name, arguments) if self._confirmer else False
                if not confirmed:
                    return self._build_response(
                        ok=False,
                        message="Action cancelled by user",
                        capability_name=capability_name,
                    )

            result = self._executor.execute(capability_name, arguments)
            if capability_name == "search_files" and result.ok and result.data:
                matches = result.data.get("matches")
                if isinstance(matches, list):
                    self._memory.set_last_search_results(matches)
            return self._build_response(
                ok=result.ok,
                message=result.message,
                capability_name=capability_name,
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
