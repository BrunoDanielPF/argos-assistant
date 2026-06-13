from collections.abc import Callable
from contextlib import nullcontext
from datetime import timedelta
import os
from pathlib import Path
import sqlite3

from jsonschema import Draft202012Validator
from langgraph.checkpoint.sqlite import SqliteSaver

from assistant.agent import AssistantAgent
from assistant.capabilities.adaptive_capability_graph import (
    AdaptiveCapabilityGraph,
)
from assistant.capabilities.model_definition_source import (
    ModelBackedToolDefinitionSource,
)
from assistant.capabilities.provisioning import CapabilityProvisioningService
from assistant.capabilities.registry import build_default_registry
from assistant.capabilities.templates import SafeToolTemplateCatalog
from assistant.capabilities.workflow_repository import (
    CapabilityWorkflowRepository,
)
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
from assistant.recovery.dry_run import DryRunBuilder
from assistant.recovery.planner import RecoveryPlanner
from assistant.recovery.policy import RecoveryPolicy
from assistant.recovery.repository import RecoveryRepository
from assistant.tools.audit import ToolAuditLog
from assistant.tools.catalog import ToolCatalog
from assistant.tools.generator import ToolDraftGenerator
from assistant.tools.installer import ToolInstaller
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
        self._capability_graph = None
        self._capability_checkpoint_connection = None

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
        tool_state_store = ToolStateStore(
            self._config.tool_state_file
        )
        capability_registry = build_default_registry(tool_catalog)
        capabilities = [
            item.name for item in capability_registry.list_all()
        ]
        session_memory = memory or SessionMemory()
        context = session_memory.snapshot()["context"]
        session_memory.set_context(
            current_cwd=context.get("current_cwd") or os.getcwd(),
            default_search_root=context.get("default_search_root") or os.getcwd(),
            user_home=context.get("user_home") or str(Path.home()),
        )
        llm_client = self._build_ollama_client()
        planner = Planner(
            llm_client,
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
                self._dynamic_tool_policy(tool_catalog, capability)
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
                planner=RecoveryPlanner(
                    policy=RecoveryPolicy(capability_registry)
                ),
                dry_run_builder=DryRunBuilder(capability_registry),
                repository=RecoveryRepository(
                    self._config.recovery_audit_file
                )
            ),
            capability_registry=capability_registry,
            capability_provisioning_service=self._build_provisioning_service(
                tool_state_store=tool_state_store,
                llm_client=llm_client,
            ),
        )

    def build_capability_graph(
        self,
        *,
        reload_session,
        execute_action,
        audit=None,
    ) -> AdaptiveCapabilityGraph:
        if self._capability_graph is not None:
            return self._capability_graph
        checkpoint_file = Path(self._config.capability_checkpoint_file)
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        self._capability_checkpoint_connection = sqlite3.connect(
            checkpoint_file,
            check_same_thread=False,
        )
        checkpointer = SqliteSaver(
            self._capability_checkpoint_connection
        )
        checkpointer.setup()
        workflow_repository = CapabilityWorkflowRepository(
            self._config.database_file,
            max_pending_per_session=(
                self._config.max_pending_capability_workflows_per_session
            ),
        )
        self._capability_graph = AdaptiveCapabilityGraph(
            provisioning_service=self._build_provisioning_service(),
            repository=workflow_repository,
            checkpointer=checkpointer,
            reload_session=reload_session,
            execute_action=execute_action,
            policy_decider=self._workflow_policy,
            dry_run_builder=self._workflow_dry_run,
            audit=audit,
            ttl=timedelta(
                hours=self._config.capability_workflow_ttl_hours
            ),
        )
        return self._capability_graph

    def _build_provisioning_service(
        self,
        *,
        tool_state_store: ToolStateStore | None = None,
        llm_client=None,
    ) -> CapabilityProvisioningService:
        state_store = tool_state_store or ToolStateStore(
            self._config.tool_state_file
        )
        client = llm_client or self._build_ollama_client()
        return CapabilityProvisioningService(
            generator=ToolDraftGenerator(
                self._config.tool_drafts_dir,
                state_store,
            ),
            state_store=state_store,
            installer=ToolInstaller(
                tools_root=self._config.tools_dir,
                envs_root=self._config.tool_envs_dir,
                state_store=state_store,
            ),
            audit_log=ToolAuditLog(self._config.tool_audit_file),
            definition_sources=[
                SafeToolTemplateCatalog(),
                ModelBackedToolDefinitionSource(client),
            ],
        )

    def _build_ollama_client(self):
        return OllamaClient(
            model=self._config.model,
            base_url=self._config.ollama_base_url,
            timeout_seconds=self._config.ollama_timeout_seconds,
            keep_alive=self._config.ollama_keep_alive,
            think=self._config.ollama_think,
            options={
                "num_predict": self._config.ollama_num_predict,
                "num_ctx": self._config.ollama_num_ctx,
            },
        )

    def _workflow_policy(
        self,
        capability: str,
        arguments: dict,
        context: dict,
    ) -> str:
        registry = build_default_registry(self.build_tool_catalog())
        return decide_policy(
            capability,
            arguments,
            context,
            registry=registry,
        )

    def _workflow_dry_run(
        self,
        capability: str,
        arguments: dict,
        context: dict,
    ) -> dict:
        registry = build_default_registry(self.build_tool_catalog())
        plan = DryRunBuilder(registry).build(capability, arguments)
        return plan.model_dump(mode="json")

    @staticmethod
    def _dynamic_tool_policy(
        tool_catalog: ToolCatalog,
        capability: str,
    ) -> str:
        tool = tool_catalog.get_enabled(capability)
        if tool is None:
            return decide_policy(capability)
        normalized = capability.casefold()
        if any(
            marker in normalized
            for marker in ("environment", ".env", "system", "shell")
        ):
            return "confirm"
        permissions = tool.manifest.permissions
        if (
            not permissions.filesystem.write
            and not permissions.network.enabled
            and not permissions.subprocess.executables
        ):
            return "allow"
        return "confirm"

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
