from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass(frozen=True)
class ToolAuditEvent:
    event: str
    invocation_id: str
    tool_name: str
    tool_version: str
    details: dict = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ToolAuditLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(self, event: ToolAuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(event), ensure_ascii=True) + "\n")
