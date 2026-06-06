import json
from pathlib import Path
import re


class PlannerError(ValueError):
    pass


CAPABILITY_ALIASES = {
    "open_app": "open_application",
    "open_document": "open_file",
    "open_path": "open_file",
    "launch_application": "open_application",
    "open_site": "open_url",
    "open_website": "open_url",
    "open_webpage": "open_url",
    "search_for_files": "search_files",
}


class Planner:
    def __init__(self, llm_client, capabilities: list[str] | None = None) -> None:
        self._llm_client = llm_client
        self._capabilities = capabilities or []

    def _build_system_prompt(self, context: dict | None = None) -> str:
        context = context or {}
        prompt = (
            "You are Argos. "
            "Return only JSON. "
            'For executable requests, use {"mode":"action","capability":"<name>","arguments":{...}}. '
            'For multi-step executable requests, use {"mode":"plan","steps":[{"capability":"<name>","arguments":{...}}]}. '
            'For direct answers, use {"mode":"answer","content":"<text>"}. '
            "Requests to open websites, search files, open applications, or run supported actions must use mode=action."
        )
        if self._capabilities:
            prompt += f" Supported capabilities: {', '.join(self._capabilities)}."
        prompt += (
            " Prefer the most specific supported capability. "
            "Do not use run_shell_command for file search when search_files fits. "
            'When responding in answer mode, identify yourself as Argos if the user asks your name or who you are.'
        )
        long_term_memories = context.get("long_term_memories")
        if isinstance(long_term_memories, list) and long_term_memories:
            prompt += " Relevant long-term memories:"
            for memory in long_term_memories[:5]:
                if isinstance(memory, dict) and isinstance(memory.get("learning"), str):
                    memory_context = memory.get("context", "geral")
                    prompt += f" [{memory_context}] {memory['learning']}"
        return prompt

    def create_plan(self, user_input: str, context: dict | None = None) -> dict:
        heuristic_plan = self._heuristic_plan(user_input, context=context)
        if heuristic_plan is not None:
            return heuristic_plan

        messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(context=context),
            },
            {"role": "user", "content": user_input},
        ]
        response = self._llm_client.chat(messages)
        response_text = self._extract_response_text(response)
        parsed = self._parse_response_text(response_text)
        return self._validate_plan_shape(parsed)

    def _heuristic_plan(self, user_input: str, context: dict | None = None) -> dict | None:
        normalized_input = user_input.strip()
        lowered_input = normalized_input.lower()
        context = context or {}

        create_markdown_plan = self._heuristic_create_markdown_plan(
            normalized_input,
            lowered_input,
            context,
        )
        if create_markdown_plan is not None:
            return create_markdown_plan

        if lowered_input.startswith("open http://") or lowered_input.startswith("open https://"):
            return {
                "mode": "action",
                "capability": "open_url",
                "arguments": {"url": normalized_input.split(" ", 1)[1].strip()},
            }

        open_file_match = re.fullmatch(r"open\s+file\s+(.+)", normalized_input, flags=re.IGNORECASE)
        if open_file_match:
            path = open_file_match.group(1).strip().strip('"')
            if path:
                return {
                    "mode": "action",
                    "capability": "open_file",
                    "arguments": {"path": path},
                }

        open_match = re.fullmatch(r"open\s+(.+)", normalized_input, flags=re.IGNORECASE)
        if open_match:
            application = open_match.group(1).strip()
            tokens = application.split()
            looks_like_website_request = any(
                token.lower() in {"website", "site", "url", "webpage", "page"}
                for token in tokens
            )
            if application and "://" not in application and len(tokens) == 1 and not looks_like_website_request:
                return {
                    "mode": "action",
                    "capability": "open_application",
                    "arguments": {"application": application},
                }

        find_match = re.fullmatch(
            r"find\s+(.+?)\s+in\s+(.+)",
            normalized_input,
            flags=re.IGNORECASE,
        )
        if find_match:
            pattern = find_match.group(1).strip().strip('"')
            root = find_match.group(2).strip().strip('"')
            if pattern and root:
                return {
                    "mode": "action",
                    "capability": "search_files",
                    "arguments": {
                        "root": root,
                        "pattern": pattern,
                        "max_results": 5,
                    },
                }

        simple_find_match = re.fullmatch(r"find\s+(.+)", normalized_input, flags=re.IGNORECASE)
        if simple_find_match:
            pattern = simple_find_match.group(1).strip().strip('"')
            root = context.get("default_search_root") or context.get("current_cwd")
            if pattern and isinstance(root, str) and root.strip():
                return {
                    "mode": "action",
                    "capability": "search_files",
                    "arguments": {
                        "root": root,
                        "pattern": pattern,
                        "max_results": 5,
                    },
                }

        return None

    def _heuristic_create_markdown_plan(
        self,
        normalized_input: str,
        lowered_input: str,
        context: dict,
    ) -> dict | None:
        wants_create = any(term in lowered_input for term in ("criar", "crie", "create"))
        wants_markdown = any(term in lowered_input for term in ("markdown", "marquidown", ".md"))
        if not wants_create or not wants_markdown:
            return None

        content = self._extract_requested_content(normalized_input)
        if not content:
            return None

        user_home = context.get("user_home") or str(Path.home())
        target_name = self._extract_markdown_filename(lowered_input, content)
        target_path = Path(str(user_home)) / target_name
        return {
            "mode": "plan",
            "steps": [
                {
                    "capability": "create_file",
                    "arguments": {"path": str(target_path), "content": content},
                },
                {
                    "capability": "open_file",
                    "arguments": {"path": str(target_path)},
                },
            ],
        }

    def _extract_requested_content(self, user_input: str) -> str | None:
        lowered = user_input.lower()
        hello_match = re.search(r"\bhello\s+world\b", lowered)
        if hello_match:
            return "hello world"

        quoted_match = re.search(r'"([^"]+)"', user_input)
        if quoted_match:
            return quoted_match.group(1).strip()

        written_match = re.search(
            r"(?:ter|com|escrito|conteudo|conteúdo)\s+(.+?)(?:\s+escrito|\s+no arquivo|$)",
            user_input,
            flags=re.IGNORECASE,
        )
        if written_match:
            return written_match.group(1).strip(" .")
        return None

    def _extract_markdown_filename(self, lowered_input: str, content: str) -> str:
        explicit_name_match = re.search(r"([\w-]+\.md)", lowered_input)
        if explicit_name_match:
            return explicit_name_match.group(1)

        slug = re.sub(r"[^a-zA-Z0-9]+", "_", content.lower()).strip("_")
        return f"{slug or 'documento'}.md"

    def _extract_response_text(self, response: dict) -> str:
        if not isinstance(response, dict):
            raise PlannerError(f"Planner expected dict response from LLM client, got {type(response).__name__}")

        response_text = response.get("response")
        if not isinstance(response_text, str) or not response_text.strip():
            raise PlannerError("Planner expected non-empty string in response['response']")
        return response_text

    def _parse_response_text(self, response_text: str) -> dict:
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise PlannerError(f"Planner received invalid JSON response: {response_text!r}") from exc

        if not isinstance(parsed, dict):
            raise PlannerError(f"Planner expected JSON object response, got {type(parsed).__name__}")
        return parsed

    def _validate_plan_shape(self, plan: dict) -> dict:
        mode = plan.get("mode")
        if not isinstance(mode, str):
            raise PlannerError("Planner response is missing required string field 'mode'")

        if mode == "action":
            capability = plan.get("capability")
            arguments = plan.get("arguments")
            action_payload = plan.get("action")

            if not isinstance(capability, str):
                if isinstance(action_payload, str):
                    capability = action_payload
                elif isinstance(action_payload, dict):
                    nested_capability = action_payload.get("name", action_payload.get("type"))
                    if isinstance(nested_capability, str):
                        capability = nested_capability
                        if not isinstance(arguments, dict):
                            arguments = {
                                key: value
                                for key, value in action_payload.items()
                                if key not in {"name", "type"}
                            }

            if not isinstance(arguments, dict):
                if "arguments" in plan:
                    arguments = None
                else:
                    derived_arguments = {
                        key: value
                        for key, value in plan.items()
                        if key not in {"mode", "capability", "action"}
                    }
                    arguments = derived_arguments if derived_arguments else None

            if not isinstance(capability, str):
                raise PlannerError("Planner action response is missing required string field 'capability'")
            capability = CAPABILITY_ALIASES.get(capability, capability)
            if not isinstance(arguments, dict):
                raise PlannerError("Planner action response is missing required dict field 'arguments'")
            return {
                "mode": "action",
                "capability": capability,
                "arguments": arguments,
            }

        if mode == "answer":
            content = plan.get("content", plan.get("response"))
            if not isinstance(content, str):
                raise PlannerError("Planner answer response is missing required string field 'content'")
            return {
                "mode": "answer",
                "content": content,
            }

        if mode == "plan":
            steps = plan.get("steps")
            if not isinstance(steps, list) or not steps:
                raise PlannerError("Planner plan response is missing required non-empty list field 'steps'")

            validated_steps = []
            for index, step in enumerate(steps):
                if not isinstance(step, dict):
                    raise PlannerError(f"Planner plan step {index} must be an object")
                capability = step.get("capability")
                arguments = step.get("arguments")
                if not isinstance(capability, str):
                    raise PlannerError(f"Planner plan step {index} is missing string field 'capability'")
                if not isinstance(arguments, dict):
                    raise PlannerError(f"Planner plan step {index} is missing dict field 'arguments'")
                validated_steps.append(
                    {
                        "capability": CAPABILITY_ALIASES.get(capability, capability),
                        "arguments": arguments,
                    }
                )
            return {"mode": "plan", "steps": validated_steps}

        raise PlannerError(f"Planner response has unsupported mode {mode!r}")
