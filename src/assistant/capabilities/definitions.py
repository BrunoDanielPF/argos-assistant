from __future__ import annotations

from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, Field

from assistant.tools.models import ToolExecution, ToolPermissions


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolDefinition(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*)+$")
    version: str = Field(
        default="1.0.0",
        pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$",
    )
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    input_schema: dict
    output_schema: dict
    permissions: ToolPermissions = Field(default_factory=ToolPermissions)
    execution: ToolExecution = Field(
        default_factory=lambda: ToolExecution(
            timeout_seconds=30,
            max_output_bytes=65_536,
        )
    )
    handler_body: str = Field(min_length=1)

    def definition_hash(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()
