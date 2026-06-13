import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
import yaml


class AppConfig(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    model: str = Field(
        default_factory=lambda: os.environ.get("ARGOS_MODEL", "argos-qwen3:4b")
    )
    ollama_base_url: str = "http://localhost:11434/api"
    ollama_timeout_seconds: float = 90.0
    ollama_keep_alive: str = "10m"
    ollama_think: bool = False
    ollama_num_predict: int = 512
    ollama_num_ctx: int = 4096
    argos_home: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("ARGOS_HOME", Path.home() / ".argos")
        )
    )
    gateway_host: Literal["127.0.0.1"] = "127.0.0.1"
    gateway_port: int = Field(default=17831, ge=1024, le=65535)
    job_scheduler_interval_seconds: float = Field(default=5.0, ge=0.1, le=3600.0)
    gateway_token_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_GATEWAY_TOKEN_FILE",
                Path.home() / ".argos" / "gateway.token",
            )
        )
    )
    gateway_pid_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_GATEWAY_PID_FILE",
                Path.home() / ".argos" / "gateway.pid",
            )
        )
    )
    gateway_log_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_GATEWAY_LOG_FILE",
                Path.home() / ".argos" / "logs" / "gateway.log",
            )
        )
    )
    database_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_DATABASE_FILE",
                Path.home() / ".argos" / "argos.db",
            )
        )
    )
    capability_checkpoint_file: Path | None = Field(
        default_factory=lambda: (
            Path(os.environ["ARGOS_CAPABILITY_CHECKPOINT_FILE"])
            if "ARGOS_CAPABILITY_CHECKPOINT_FILE" in os.environ
            else None
        )
    )
    capability_workflow_ttl_hours: int = Field(default=24, ge=1, le=720)
    max_pending_capability_workflows_per_session: int = Field(
        default=3,
        ge=1,
        le=20,
    )
    event_log_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_EVENT_LOG_FILE",
                Path.home() / ".argos" / "logs" / "events.jsonl",
            )
        )
    )
    direct_mode: bool = False
    memory_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("ARGOS_MEMORY_DIR", Path.home() / ".argos" / "memory")
        )
    )
    memory_auto_save_low_risk: bool = False
    tools_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get("ARGOS_TOOLS_DIR", Path.home() / ".argos" / "tools")
        )
    )
    tool_drafts_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_TOOL_DRAFTS_DIR",
                Path.home() / ".argos" / "tool-drafts",
            )
        )
    )
    tool_envs_dir: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_TOOL_ENVS_DIR",
                Path.home() / ".argos" / "tool-envs",
            )
        )
    )
    tool_state_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_TOOL_STATE_FILE",
                Path.home() / ".argos" / "tool-state.json",
            )
        )
    )
    tool_audit_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_TOOL_AUDIT_FILE",
                Path.home() / ".argos" / "audit" / "tools.jsonl",
            )
        )
    )
    recovery_audit_file: Path = Field(
        default_factory=lambda: Path(
            os.environ.get(
                "ARGOS_RECOVERY_AUDIT_FILE",
                Path.home() / ".argos" / "audit" / "recovery.jsonl",
            )
        )
    )

    @model_validator(mode="before")
    @classmethod
    def resolve_argos_home_paths(cls, values):
        if not isinstance(values, dict):
            return values
        resolved = dict(values)
        argos_home = Path(
            resolved.get(
                "argos_home",
                os.environ.get("ARGOS_HOME", Path.home() / ".argos"),
            )
        )
        relative_defaults = {
            "gateway_token_file": (
                "ARGOS_GATEWAY_TOKEN_FILE",
                "gateway.token",
            ),
            "gateway_pid_file": ("ARGOS_GATEWAY_PID_FILE", "gateway.pid"),
            "gateway_log_file": (
                "ARGOS_GATEWAY_LOG_FILE",
                Path("logs") / "gateway.log",
            ),
            "database_file": ("ARGOS_DATABASE_FILE", "argos.db"),
            "capability_checkpoint_file": (
                "ARGOS_CAPABILITY_CHECKPOINT_FILE",
                "capability-checkpoints.db",
            ),
            "event_log_file": (
                "ARGOS_EVENT_LOG_FILE",
                Path("logs") / "events.jsonl",
            ),
            "memory_dir": ("ARGOS_MEMORY_DIR", "memory"),
            "tools_dir": ("ARGOS_TOOLS_DIR", "tools"),
            "tool_drafts_dir": (
                "ARGOS_TOOL_DRAFTS_DIR",
                "tool-drafts",
            ),
            "tool_envs_dir": ("ARGOS_TOOL_ENVS_DIR", "tool-envs"),
            "tool_state_file": (
                "ARGOS_TOOL_STATE_FILE",
                "tool-state.json",
            ),
            "tool_audit_file": (
                "ARGOS_TOOL_AUDIT_FILE",
                Path("audit") / "tools.jsonl",
            ),
            "recovery_audit_file": (
                "ARGOS_RECOVERY_AUDIT_FILE",
                Path("audit") / "recovery.jsonl",
            ),
        }
        resolved.setdefault("argos_home", argos_home)
        for field_name, (env_name, relative_path) in relative_defaults.items():
            resolved.setdefault(
                field_name,
                Path(os.environ[env_name])
                if env_name in os.environ
                else argos_home / relative_path,
            )
        return resolved

    @model_validator(mode="after")
    def resolve_capability_checkpoint_file(self):
        if self.capability_checkpoint_file is None:
            self.capability_checkpoint_file = (
                self.argos_home / "capability-checkpoints.db"
            )
        return self

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        default_home = Path(
            os.environ.get("ARGOS_HOME", Path.home() / ".argos")
        )
        config_path = path or Path(
            os.environ.get(
                "ARGOS_CONFIG_FILE",
                default_home / "config.yaml",
            )
        )
        values: dict = {}
        if config_path.exists():
            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if loaded is not None:
                if not isinstance(loaded, dict):
                    raise ValueError("Argos config must contain a YAML mapping")
                values.update(loaded)

        env_fields = {
            "ARGOS_MODEL": "model",
            "ARGOS_OLLAMA_BASE_URL": "ollama_base_url",
            "ARGOS_OLLAMA_TIMEOUT_SECONDS": "ollama_timeout_seconds",
            "ARGOS_OLLAMA_KEEP_ALIVE": "ollama_keep_alive",
            "ARGOS_OLLAMA_THINK": "ollama_think",
            "ARGOS_OLLAMA_NUM_PREDICT": "ollama_num_predict",
            "ARGOS_OLLAMA_NUM_CTX": "ollama_num_ctx",
            "ARGOS_HOME": "argos_home",
            "ARGOS_GATEWAY_HOST": "gateway_host",
            "ARGOS_GATEWAY_PORT": "gateway_port",
            "ARGOS_JOB_SCHEDULER_INTERVAL_SECONDS": "job_scheduler_interval_seconds",
            "ARGOS_GATEWAY_TOKEN_FILE": "gateway_token_file",
            "ARGOS_GATEWAY_PID_FILE": "gateway_pid_file",
            "ARGOS_GATEWAY_LOG_FILE": "gateway_log_file",
            "ARGOS_DATABASE_FILE": "database_file",
            "ARGOS_CAPABILITY_CHECKPOINT_FILE": (
                "capability_checkpoint_file"
            ),
            "ARGOS_CAPABILITY_WORKFLOW_TTL_HOURS": (
                "capability_workflow_ttl_hours"
            ),
            "ARGOS_MAX_PENDING_CAPABILITY_WORKFLOWS_PER_SESSION": (
                "max_pending_capability_workflows_per_session"
            ),
            "ARGOS_EVENT_LOG_FILE": "event_log_file",
            "ARGOS_MEMORY_DIR": "memory_dir",
            "ARGOS_MEMORY_AUTO_SAVE_LOW_RISK": "memory_auto_save_low_risk",
            "ARGOS_TOOLS_DIR": "tools_dir",
            "ARGOS_TOOL_DRAFTS_DIR": "tool_drafts_dir",
            "ARGOS_TOOL_ENVS_DIR": "tool_envs_dir",
            "ARGOS_TOOL_STATE_FILE": "tool_state_file",
            "ARGOS_TOOL_AUDIT_FILE": "tool_audit_file",
            "ARGOS_RECOVERY_AUDIT_FILE": "recovery_audit_file",
        }
        for env_name, field_name in env_fields.items():
            if env_name in os.environ:
                values[field_name] = os.environ[env_name]
        return cls.model_validate(values)
