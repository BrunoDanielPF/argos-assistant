import json

from fastapi.testclient import TestClient

from assistant.capabilities.provisioning import CapabilityProvisioningService
from assistant.capabilities.registry import build_default_registry
from assistant.gateway.app import create_gateway_app
from assistant.gateway.auth import LocalTokenStore
from assistant.gateway.service import GatewayService
from assistant.agent import AssistantAgent
from assistant.execution.executor import ActionExecutor
from assistant.memory.session import SessionMemory
from assistant.planner import Planner
from assistant.recovery.dry_run import DryRunBuilder
from assistant.recovery.engine import RecoveryEngine
from assistant.recovery.planner import RecoveryPlanner
from assistant.recovery.policy import RecoveryPolicy
from assistant.recovery.repository import RecoveryRepository
from assistant.runtime.contracts import AgentRequest
from assistant.sessions.repository import SessionRepository
from assistant.tools.audit import ToolAuditEvent, ToolAuditLog
from assistant.tools.catalog import ToolCatalog
from assistant.tools.generator import ToolDraftGenerator
from assistant.tools.installer import ToolInstaller
from assistant.tools.runner import ToolRunResult
from assistant.tools.state import ToolStateStore


class StatefulAgent:
    def __init__(self, memory):
        self.memory = memory

    def handle(self, content):
        self.memory.add_user_message(content)
        previous_turns = len(self.memory.snapshot()["history"])
        message = f"turn {previous_turns}: {content}"
        self.memory.add_assistant_message(message)
        return {"ok": True, "message": message, "suggestions": []}


class StatefulFactory:
    def build_agent(self, memory=None, confirmer=None):
        return StatefulAgent(memory or SessionMemory())


def build_app(database, token_store):
    repository = SessionRepository(database)
    service = GatewayService(StatefulFactory(), repository)
    app = create_gateway_app(
        service=service,
        token_store=token_store,
        repository=repository,
        model_name="test-model",
    )
    return app, repository


def test_gateway_restores_conversation_after_service_restart(tmp_path):
    database = tmp_path / "argos.db"
    token_store = LocalTokenStore(
        tmp_path / "gateway.token",
        permission_hardener=lambda path: None,
    )
    token = token_store.get_or_create()
    headers = {"Authorization": f"Bearer {token}"}

    first_app, first_repository = build_app(database, token_store)
    with TestClient(first_app) as client:
        response = client.post(
            "/v1/chat",
            headers=headers,
            json={"session_id": "default", "content": "primeiro"},
        )
        assert response.status_code == 200
    first_repository.close()

    second_app, second_repository = build_app(database, token_store)
    with TestClient(second_app) as client:
        response = client.post(
            "/v1/chat",
            headers=headers,
            json={"session_id": "default", "content": "segundo"},
        )
        history = client.get(
            "/v1/sessions/default",
            headers=headers,
        ).json()["history"]

    assert response.status_code == 200
    assert [item["content"] for item in history] == [
        "primeiro",
        "turn 1: primeiro",
        "segundo",
        "turn 3: segundo",
    ]
    second_repository.close()


def test_gateway_creates_file_only_after_confirmation(tmp_path):
    target = tmp_path / "receita.md"

    class CreateFilePlanner:
        def create_plan(self, user_input):
            return {
                "mode": "action",
                "capability": "create_file",
                "arguments": {
                    "path": str(target),
                    "content": "# Receita\n\nPao de forma",
                },
            }

    class AgentFactory:
        def build_agent(self, memory=None, confirmer=None):
            return AssistantAgent(
                planner=CreateFilePlanner(),
                executor=ActionExecutor(),
                memory=memory,
            )

    repository = SessionRepository(tmp_path / "argos.db")
    service = GatewayService(AgentFactory(), repository)
    request = service.handle(
        AgentRequest(
            session_id="default",
            content="salve a receita",
        )
    )

    assert request.status == "waiting_confirmation"
    assert not target.exists()

    result = service.resolve_confirmation(
        request.confirmation.confirmation_id,
        approved=True,
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "# Receita\n\nPao de forma"
    repository.close()


def test_environment_capability_gap_enables_reloads_and_retries(tmp_path):
    class FailIfCalledClient:
        def chat(self, messages):
            raise AssertionError("environment route must be deterministic")

    class FakeEnvironmentRunner:
        def __init__(self, audit_log):
            self.audit_log = audit_log
            self.calls = []

        def run(self, tool, arguments):
            self.calls.append((tool.manifest.name, arguments))
            for event in ("execution_started", "execution_finished"):
                self.audit_log.write(
                    ToolAuditEvent(
                        event=event,
                        invocation_id="fake-environment-run",
                        tool_name=tool.manifest.name,
                        tool_version=tool.manifest.version,
                    )
                )
            return ToolRunResult(
                ok=True,
                result={
                    "name": arguments["name"],
                    "scope": "user",
                    "updated": True,
                },
            )

    class LifecycleFactory:
        def __init__(self):
            self.state_store = ToolStateStore(
                tmp_path / "tool-state.json"
            )
            self.audit_log = ToolAuditLog(
                tmp_path / "tools-audit.jsonl"
            )
            self.runner = FakeEnvironmentRunner(self.audit_log)
            self.build_count = 0

        def build_agent(self, memory=None, confirmer=None):
            self.build_count += 1
            catalog = ToolCatalog(
                tools_root=tmp_path / "tools",
                state_store=self.state_store,
            )
            registry = build_default_registry(catalog)
            executor = ActionExecutor(
                tool_catalog=catalog,
                tool_runner=self.runner,
            )
            provisioning = CapabilityProvisioningService(
                generator=ToolDraftGenerator(
                    tmp_path / "drafts",
                    self.state_store,
                ),
                state_store=self.state_store,
                installer=ToolInstaller(
                    tools_root=tmp_path / "tools",
                    envs_root=tmp_path / "envs",
                    state_store=self.state_store,
                    create_environment=False,
                ),
                audit_log=self.audit_log,
            )
            return AssistantAgent(
                planner=Planner(
                    FailIfCalledClient(),
                    capabilities=[
                        item.name for item in registry.list_all()
                    ],
                ),
                executor=executor,
                memory=memory or SessionMemory(),
                capability_registry=registry,
                capability_provisioning_service=provisioning,
                recovery_engine=RecoveryEngine(
                    planner=RecoveryPlanner(
                        policy=RecoveryPolicy(registry)
                    ),
                    dry_run_builder=DryRunBuilder(registry),
                    repository=RecoveryRepository(
                        tmp_path / "recovery.jsonl"
                    ),
                ),
            )

    repository = SessionRepository(tmp_path / "argos.db")
    factory = LifecycleFactory()
    service = GatewayService(factory, repository)

    proposal = service.handle(
        AgentRequest(
            session_id="default",
            content=(
                "configure uma variável de ambiente chamada "
                "ARGOS_TESTE_NOVA com valor 456"
            ),
        )
    )
    draft = service.resolve_confirmation(
        proposal.confirmation.confirmation_id,
        approved=True,
    )
    assert draft.status == "waiting_confirmation"
    assert draft.confirmation.capability == (
        "tool.approve_install_enable"
    )
    assert draft.confirmation.permissions == [
        "approve:local_tool",
        "install:local_tool",
        "enable:local_tool",
        "execute:none",
    ]
    retry = service.resolve_confirmation(
        draft.confirmation.confirmation_id,
        approved=True,
    )

    assert factory.build_count == 2
    assert retry.status == "waiting_confirmation"
    assert retry.confirmation.capability == (
        "local.windows.env_set_user"
    )
    assert retry.confirmation.arguments_summary == {
        "name": "ARGOS_TESTE_NOVA",
        "value": "456",
    }
    assert retry.confirmation.dry_run["requires_confirmation"] is True
    assert retry.confirmation.permissions == [
        "windows_registry:user_environment",
        "filesystem_write:none",
        "network:none",
        "subprocess:none",
    ]
    assert factory.runner.calls == []

    executed = service.resolve_confirmation(
        retry.confirmation.confirmation_id,
        approved=True,
    )

    assert executed.ok is True
    assert factory.runner.calls == [
        (
            "local.windows.env_set_user",
            {"name": "ARGOS_TESTE_NOVA", "value": "456"},
        )
    ]
    assert all(
        capability != "file.write"
        for capability, _ in factory.runner.calls
    )
    state = factory.state_store.get(
        "local.windows.env_set_user",
        "1.0.0",
    )
    assert state.state == "enabled"
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "tools-audit.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert events == [
        "draft_proposed",
        "draft_created",
        "tool_approved",
        "tool_installed",
        "tool_enabled",
        "registry_reloaded",
        "retry_confirmation_required",
        "retry_confirmed",
        "execution_started",
        "execution_finished",
        "retry_executed",
    ]
    recovery = [
        json.loads(line)
        for line in (tmp_path / "recovery.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert recovery[0]["event"]["failure_type"] == "capability_gap"

    repeated = service.handle(
        AgentRequest(
            session_id="default",
            content=(
                "configure uma variável de ambiente chamada "
                "ARGOS_TESTE_OUTRA com valor 789"
            ),
        )
    )
    assert repeated.status == "waiting_confirmation"
    assert repeated.confirmation.capability == (
        "local.windows.env_set_user"
    )
    assert repeated.error_code is None
    assert len(
        (tmp_path / "recovery.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ) == 1
    repository.close()
