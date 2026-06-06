from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FilesystemPermissions(StrictModel):
    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)


class NetworkPermissions(StrictModel):
    enabled: bool = False
    hosts: list[str] = Field(default_factory=list)


class SubprocessPermissions(StrictModel):
    executables: list[str] = Field(default_factory=list)


class ToolPermissions(StrictModel):
    filesystem: FilesystemPermissions = Field(default_factory=FilesystemPermissions)
    network: NetworkPermissions = Field(default_factory=NetworkPermissions)
    subprocess: SubprocessPermissions = Field(default_factory=SubprocessPermissions)


class ToolRuntime(StrictModel):
    type: Literal["python"]
    python: str
    entrypoint: str


class ToolExecution(StrictModel):
    timeout_seconds: int = Field(ge=1, le=300)
    max_output_bytes: int = Field(ge=1024, le=10_485_760)


class ToolManifest(StrictModel):
    schema_version: Literal["1.0"]
    name: str = Field(pattern=r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_]*)+$")
    version: str = Field(pattern=r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    runtime: ToolRuntime
    input_schema: dict
    output_schema: dict
    permissions: ToolPermissions = Field(default_factory=ToolPermissions)
    execution: ToolExecution
