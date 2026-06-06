import os
from pathlib import Path

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    model: str = "argos-qwen3:4b"
    ollama_base_url: str = "http://localhost:11434/api"
    ollama_timeout_seconds: float = 90.0
    ollama_keep_alive: str = "10m"
    ollama_think: bool = False
    ollama_num_predict: int = 512
    ollama_num_ctx: int = 4096
    memory_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("ARGOS_MEMORY_DIR", Path.home() / ".argos" / "memory")
        )
    )
