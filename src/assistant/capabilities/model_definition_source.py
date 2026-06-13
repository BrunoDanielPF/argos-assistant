from __future__ import annotations

import json

from assistant.capabilities.definitions import ToolDefinition
from assistant.workflows.redaction import redact_sensitive


class ModelBackedToolDefinitionSource:
    def __init__(self, llm_client) -> None:
        self._llm_client = llm_client

    def build_candidate(
        self,
        *,
        requested_capability: str,
        user_goal: str,
        arguments: dict,
        platform_context: dict,
        original_action: dict,
    ) -> ToolDefinition | None:
        schema = ToolDefinition.model_json_schema()
        safe_context = {
            "requested_capability": requested_capability,
            "user_goal": user_goal,
            "arguments": redact_sensitive(arguments),
            "platform_context": redact_sensitive(platform_context),
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "Propose exactly one strictly read-only local Argos tool "
                    "as structured JSON matching the provided schema. "
                    "Use only Python standard library. Define only "
                    "run(arguments). Do not use filesystem writes, network, "
                    "subprocess, shell, environment mutation, system "
                    "configuration, dependencies, dynamic imports, or "
                    "top-level effects. Use closed JSON schemas and minimum "
                    "filesystem read permissions based on input placeholders. "
                    "Return JSON only. Schema: "
                    + json.dumps(schema, ensure_ascii=True, sort_keys=True)
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    safe_context,
                    ensure_ascii=True,
                    sort_keys=True,
                ),
            },
        ]
        response = self._llm_client.chat_structured(messages, schema)
        return ToolDefinition.model_validate_json(response["response"])
