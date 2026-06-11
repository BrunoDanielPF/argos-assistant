from collections.abc import Callable
from contextlib import nullcontext
import os
from pathlib import Path

from jsonschema import Draft202012Validator

from assistant.agent import AssistantAgent
from assistant.capabilities.registry import build_default_registry
from assistant.config import AppConfig
from assistant.execution.executor import ActionExecutor
from assistant.jobs.repository import JobRepository
from assistant.execution.policy import decide_policy
from assistant.files.resolver import FileResolver
from assistant.llm.ollama_client import OllamaClient
from assistant.memory.classifier import MemoryClassifier
from assistant.memory.engine import MemoryEngine
from assistant.memory.long_term import LongTermMemoryStore
from assistant.memory.migration import MarkdownMemoryMigrator
from assistant.memory.policy import MemoryPolicy
from assistant.memory.repository import MemoryRepository
from assistant.memory.session import SessionMemory
from assistant.planner import Planner
from assistant.recovery.engine import RecoveryEngine
from assistant.recovery.repository import RecoveryRepository
from assistant.tools.audit import ToolAuditLog
from assistant.tools.catalog import ToolCatalog
from assistant.tools.runner import ToolRunner
from assistant.tools.state import ToolStateStore


class RuntimeFactory:
    def __init__(
        self,
        config: AppConfig,
        loading_context: Callable | None = None,
        memory_engine=None,
    ) -> None:
        self._config = config
        self._loading_context = loading_context or (lambda: nullcontext())
        self._memory_engine = memory_engine

    def _get_memory_engine(self):
        if self._memory_engine is None:
            repository = MemoryRepository(self._config.database_file)
            legacy_store = LongTermMemoryStore(self._config.memory_dir)
            MarkdownMemoryMigrator(repository, legacy_store).migrate()
            self._memory_engine = MemoryEngine(
                repository=repository,
                classifier=MemoryClassifier(
                    MemoryPolicy(
                        allow_auto_save_low_risk=(
                            self._config.memory_auto_save_low_risk
                        )
                    )
                ),
            )
        return self._memory_engine

    def build_tool_catalog(self) -> ToolCatalog:
        bundled_root = Path(__file__).resolve().parents[3] / "tools"
        return ToolCatalog(
            tools_root=self._config.tools_dir,
            state_store=ToolStateStore(self._config.tool_state_file),
            bundled_root=bundled_root,
            envs_root=self._config.tool_envs_dir,
        )

    def build_agent(
        self,
        memory: SessionMemory | None = None,
        confirmer=None,
    ) -> AssistantAgent:
        tool_catalog = self.build_tool_catalog()
        capabilities = [
            item.name for item in build_default_registry(tool_catalog).list_all()
        ]
        session_memory = memory or SessionMemory()
        context = session_memory.snapshot()["context"]
        session_memory.set_context(
            current_cwd=context.get("current_cwd") or os.getcwd(),
            default_search_root=context.get("default_search_root") or os.getcwd(),
            user_home=context.get("user_home") or str(Path.home()),
        )
        planner = Planner(
            OllamaClient(
                model=self._config.model,
                base_url=self._config.ollama_base_url,
                timeout_seconds=self._config.ollama_timeout_seconds,
                keep_alive=self._config.ollama_keep_alive,
                think=self._config.ollama_think,
                options={
                    "num_predict": self._config.ollama_num_predict,
                    "num_ctx": self._config.ollama_num_ctx,
                },
            ),
            capabilities=capabilities,
            loading_context=self._loading_context,
            tool_definitions=[
                {
                    "name": tool.manifest.name,
                    "description": tool.manifest.description,
                    "input_schema": tool.manifest.input_schema,
                }
                for tool in tool_catalog.list_enabled()
            ],
        )
        executor = ActionExecutor(
            job_repository=JobRepository(self._config.database_file),
        )
        if hasattr(executor, "configure_tools"):
            executor.configure_tools(
                tool_catalog,
                ToolRunner(
                    audit_log=ToolAuditLog(self._config.tool_audit_file)
                ),
            )
        return AssistantAgent(
            planner=planner,
            executor=executor,
            memory=session_memory,
            memory_engine=self._get_memory_engine(),
            long_term_memory=LongTermMemoryStore(self._config.memory_dir),
            policy_decider=lambda capability: (
                "confirm"
                if tool_catalog.get_enabled(capability) is not None
                else decide_policy(capability)
            ),
            action_validator=lambda capability, arguments: self._validate_tool_action(
                tool_catalog,
                capability,
                arguments,
            ),
            confirmer=confirmer,
            file_resolver=FileResolver(),
            recovery_engine=RecoveryEngine(
                repository=RecoveryRepository(
                    self._config.recovery_audit_file
                )
            ),
        )

    @staticmethod
    def _validate_tool_action(
        tool_catalog: ToolCatalog,
        capability: str,
        arguments: dict,
    ) -> str | None:
        tool = tool_catalog.get_enabled(capability)
        if tool is None:
            return None
        errors = sorted(
            Draft202012Validator(tool.manifest.input_schema).iter_errors(arguments),
            key=lambda error: list(error.path),
        )
        if not errors:
            return None
        required = tool.manifest.input_schema.get("required", [])
        missing = [
            field
            for field in required
            if isinstance(field, str) and field not in arguments
        ]
        if missing:
            return (
                f"Faltam dados para executar {capability}: "
                f"{', '.join(missing)}."
            )
        return f"Dados invalidos para executar {capability}: {errors[0].message}."
