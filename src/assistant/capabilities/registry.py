from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ActionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathAction(ActionSchema):
    path: str = Field(min_length=1)


class FileCreateAction(PathAction):
    content: str = ""


class FileWriteAction(PathAction):
    content: str
    mode: Literal["overwrite", "append"] | None = None


class FileDeleteDryRunAction(PathAction):
    pattern: str = Field(min_length=1)


class FileDeleteOneAction(PathAction):
    recursive: bool = False


class FileMoveManyAction(ActionSchema):
    destination: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    source_root: str | None = None
    pattern: str | None = None

    @model_validator(mode="after")
    def validate_source_selection(self):
        if self.sources:
            return self
        if self.source_root and self.pattern:
            return self
        raise ValueError(
            "provide sources or both source_root and pattern"
        )


class FilesSearchAction(ActionSchema):
    root: str = Field(min_length=1)
    pattern: str = Field(min_length=1)
    max_results: int = Field(default=5, ge=1, le=100)


class OpenApplicationAction(ActionSchema):
    application: str = Field(min_length=1)


class OpenUrlAction(ActionSchema):
    url: str = Field(min_length=1)


class ScheduleReminderAction(ActionSchema):
    content: str = Field(min_length=1)
    scheduled_for: str = Field(min_length=1)
    session_id: str = "default"


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    schema: type[ActionSchema]
    policy: Literal["allow", "confirm", "blocked"]
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionValidation:
    ok: bool
    capability: Capability | None = None
    arguments: dict | None = None
    error_code: str | None = None
    message: str | None = None


class CapabilityRegistry:
    def __init__(self, capabilities: list[Capability]) -> None:
        self._capabilities = {item.name: item for item in capabilities}
        self._aliases = {
            alias: item.name
            for item in capabilities
            for alias in item.aliases
        }

    def list_all(self) -> list[Capability]:
        return list(self._capabilities.values())

    def resolve(self, name: str) -> Capability | None:
        canonical = self._aliases.get(name, name)
        return self._capabilities.get(canonical)

    def get(self, name: str) -> Capability | None:
        return self.resolve(name)

    def validate(self, name: str, arguments: dict) -> ActionValidation:
        capability = self.resolve(name)
        if capability is None:
            return ActionValidation(
                ok=False,
                error_code="unsupported_capability",
                message=f"Unsupported capability: {name}",
            )
        try:
            validated = capability.schema.model_validate(arguments)
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(item) for item in first["loc"])
            detail = first["msg"]
            return ActionValidation(
                ok=False,
                capability=capability,
                error_code="invalid_schema",
                message=(
                    f"Invalid schema for {capability.name}: "
                    f"{location or 'arguments'}: {detail}"
                ),
            )
        return ActionValidation(
            ok=True,
            capability=capability,
            arguments=validated.model_dump(),
        )


def build_default_registry(tool_catalog=None) -> CapabilityRegistry:
    capabilities = [
        Capability(
            name="file.create",
            description="Create a local file with content",
            schema=FileCreateAction,
            policy="confirm",
            aliases=("create_file",),
        ),
        Capability(
            name="file.write",
            description="Overwrite or append content in an existing file",
            schema=FileWriteAction,
            policy="confirm",
            aliases=("write_file",),
        ),
        Capability(
            name="file.read",
            description="Read a local text file",
            schema=PathAction,
            policy="allow",
            aliases=("read_file",),
        ),
        Capability(
            name="file.open",
            description="Open a local file with its default application",
            schema=PathAction,
            policy="allow",
            aliases=("open_file", "open_document", "open_path"),
        ),
        Capability(
            name="file.create_directory",
            description="Create a local directory",
            schema=PathAction,
            policy="confirm",
            aliases=("create_directory",),
        ),
        Capability(
            name="file.delete_dry_run",
            description="List files that a delete operation would affect",
            schema=FileDeleteDryRunAction,
            policy="allow",
            aliases=(
                "delete_files_dry_run",
                "delete_files",
                "file.delete_many",
            ),
        ),
        Capability(
            name="file.delete_one",
            description="Delete one local file",
            schema=FileDeleteOneAction,
            policy="confirm",
            aliases=("delete_file",),
        ),
        Capability(
            name="file.move_many",
            description="Move selected files to a directory",
            schema=FileMoveManyAction,
            policy="confirm",
            aliases=("move_files", "files.move"),
        ),
        Capability(
            name="files.search",
            description="Search files in a directory",
            schema=FilesSearchAction,
            policy="allow",
            aliases=("search_files", "search_for_files"),
        ),
        Capability(
            name="open_application",
            description="Open a local application",
            schema=OpenApplicationAction,
            policy="allow",
            aliases=("open_app", "launch_application"),
        ),
        Capability(
            name="open_url",
            description="Open a URL in the browser",
            schema=OpenUrlAction,
            policy="allow",
            aliases=("open_site", "open_website", "open_webpage"),
        ),
        Capability(
            name="schedule_reminder",
            description="Schedule a local reminder",
            schema=ScheduleReminderAction,
            policy="confirm",
        ),
    ]
    if tool_catalog is not None:
        capabilities.extend(
            Capability(
                name=tool.manifest.name,
                description=tool.manifest.description,
                schema=_dynamic_schema(tool.manifest.input_schema),
                policy=_dynamic_policy(
                    tool.manifest.name,
                    tool.manifest.permissions,
                ),
            )
            for tool in tool_catalog.list_enabled()
        )
    return CapabilityRegistry(capabilities)


def _dynamic_policy(name: str, permissions) -> Literal["allow", "confirm"]:
    normalized = name.casefold()
    if any(
        marker in normalized
        for marker in ("environment", ".env", "system", "shell")
    ):
        return "confirm"
    if (
        not permissions.filesystem.write
        and not permissions.network.enabled
        and not permissions.subprocess.executables
    ):
        return "allow"
    return "confirm"


def _dynamic_schema(schema: dict) -> type[ActionSchema]:
    required = {
        field
        for field in schema.get("required", [])
        if isinstance(field, str)
    }

    class DynamicAction(ActionSchema):
        model_config = ConfigDict(extra="allow")

        @model_validator(mode="before")
        @classmethod
        def validate_required_fields(cls, value):
            if not isinstance(value, dict):
                raise ValueError("arguments must be an object")
            missing = sorted(required.difference(value))
            if missing:
                raise ValueError(
                    f"missing required fields: {', '.join(missing)}"
                )
            return value

    return DynamicAction
