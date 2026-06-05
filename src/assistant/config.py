from pydantic import BaseModel


class AppConfig(BaseModel):
    model: str = "qwen3:4b"
    ollama_base_url: str = "http://localhost:11434/api"
    ollama_timeout_seconds: float = 90.0
