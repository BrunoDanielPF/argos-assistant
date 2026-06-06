import os
from pathlib import Path

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    model: str = "argos-qwen3:4b"
    ollama_base_url: str = "http://localhost:11434/api"
    ollama_timeout_seconds: float = 90.0
    memory_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("ARGOS_MEMORY_DIR", Path.home() / ".argos" / "memory")
        )
    )
