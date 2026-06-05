from pydantic import BaseModel


class Capability(BaseModel):
    name: str
    description: str


class CapabilityRegistry:
    def __init__(self, capabilities: list[Capability]) -> None:
        self._capabilities = capabilities

    def list_all(self) -> list[Capability]:
        return list(self._capabilities)

    def get(self, name: str) -> Capability | None:
        for capability in self._capabilities:
            if capability.name == name:
                return capability
        return None


def build_default_registry() -> CapabilityRegistry:
    return CapabilityRegistry(
        [
            Capability(name="open_application", description="Open a local application"),
            Capability(name="open_file", description="Open a local file"),
            Capability(name="open_url", description="Open a URL in the browser"),
            Capability(name="search_files", description="Search files in a directory"),
            Capability(name="run_shell_command", description="Run a shell command"),
        ]
    )
