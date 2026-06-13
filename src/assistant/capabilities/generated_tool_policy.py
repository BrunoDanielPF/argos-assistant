from __future__ import annotations

from dataclasses import dataclass, field
import re

from jsonschema import Draft202012Validator

from assistant.capabilities.definitions import ToolDefinition
from assistant.tools.validator import ToolValidator


@dataclass(frozen=True)
class GeneratedToolSafetyDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


class GeneratedToolSafetyPolicy:
    _read_pattern = re.compile(
        r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}(?:[/\\]\*\*)?$"
    )

    def __init__(self, validator: ToolValidator | None = None) -> None:
        self._validator = validator or ToolValidator()

    def evaluate(
        self,
        definition: ToolDefinition,
    ) -> GeneratedToolSafetyDecision:
        reasons: list[str] = []
        permissions = definition.permissions
        if permissions.filesystem.write:
            reasons.append("filesystem_write_not_allowed")
        if permissions.network.enabled or permissions.network.hosts:
            reasons.append("network_not_allowed")
        if permissions.subprocess.executables:
            reasons.append("subprocess_not_allowed")

        reasons.extend(
            self._validate_schema("input", definition.input_schema)
        )
        reasons.extend(
            self._validate_schema("output", definition.output_schema)
        )
        input_properties = definition.input_schema.get("properties")
        input_properties = (
            input_properties if isinstance(input_properties, dict) else {}
        )
        for pattern in permissions.filesystem.read:
            match = self._read_pattern.fullmatch(pattern)
            if match is None:
                reasons.append(
                    "filesystem_read_must_use_input_placeholder"
                )
                continue
            if match.group(1) not in input_properties:
                reasons.append(
                    "filesystem_read_placeholder_missing_from_schema"
                )

        report = self._validator.validate_read_only_source(
            definition.handler_body
        )
        reasons.extend(
            (
                f"{finding.code}:{finding.message.removeprefix('unknown call: ')}"
                if finding.code == "unknown_call"
                else finding.code
            )
            for finding in report.findings
        )
        unique_reasons = list(dict.fromkeys(reasons))
        return GeneratedToolSafetyDecision(
            allowed=not unique_reasons,
            reasons=unique_reasons,
        )

    @staticmethod
    def _validate_schema(label: str, schema: dict) -> list[str]:
        reasons = []
        try:
            Draft202012Validator.check_schema(schema)
        except Exception:
            return [f"{label}_schema_invalid"]
        if schema.get("type") != "object":
            reasons.append(f"{label}_schema_must_be_object")
        if schema.get("additionalProperties") is not False:
            reasons.append(f"{label}_schema_must_be_closed")
        if not isinstance(schema.get("properties"), dict):
            reasons.append(f"{label}_schema_properties_required")
        return reasons
