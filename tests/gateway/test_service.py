import json

from assistant.gateway.service import GatewayService
from assistant.memory.session import SessionMemory
from assistant.observability.events import EventLog
from assistant.runtime.contracts import AgentRequest
from assistant.sessions.repository import SessionRepository


class FakeAgent:
    def __init__(self, memory):
        self.memory = memory

    def handle(self, content):
        self.memory.add_user_message(content)
        message = f"handled {content}"
        self.memory.add_assistant_message(message)
        return {"ok": True, "message": message, "suggestions": []}


class FakeRuntimeFactory:
    def __init__(self):
        self.build_count = 0

    def build_agent(self, memory=None, confirmer=None):
        self.build_count += 1
        return FakeAgent(memory or SessionMemory())


def test_service_reuses_and_persists_session(tmp_path):
    repository = SessionRepository(tmp_path / "argos.db")
    factory = FakeRuntimeFactory()
    service = GatewayService(factory, repository)

    first = service.handle(AgentRequest(session_id="s1", content="conte"))
    second = service.handle(AgentRequest(session_id="s1", content="2"))

    assert first.session_id == "s1"
    assert second.session_id == "s1"
    assert factory.build_count == 1
    assert [item["content"] for item in repository.load("s1")["history"]] == [
        "conte",
        "handled conte",
        "2",
        "handled 2",
    ]
    repository.close()


def test_service_restores_session_after_new_service_instance(tmp_path):
    database = tmp_path / "argos.db"
    repository = SessionRepository(database)
    first = GatewayService(FakeRuntimeFactory(), repository)
    first.handle(AgentRequest(session_id="s1", content="primeiro"))

    second_factory = FakeRuntimeFactory()
    second = GatewayService(second_factory, repository)
    second.handle(AgentRequest(session_id="s1", content="segundo"))

    history = repository.load("s1")["history"]
    assert history[0]["content"] == "primeiro"
    assert history[-1]["content"] == "handled segundo"
    assert second_factory.build_count == 1
    repository.close()


def test_service_emits_metadata_without_prompt(tmp_path):
    repository = SessionRepository(tmp_path / "argos.db")
    event_path = tmp_path / "events.jsonl"
    service = GatewayService(
        FakeRuntimeFactory(),
        repository,
        event_log=EventLog(event_path),
    )

    service.handle(AgentRequest(session_id="s1", content="segredo pessoal"))

    events = [
        json.loads(line)
        for line in event_path.read_text(encoding="utf-8").splitlines()
    ]
    assert events[-1]["kind"] == "request_finished"
    assert "duration_ms" in events[-1]["details"]
    assert "segredo pessoal" not in event_path.read_text(encoding="utf-8")
    repository.close()


def test_service_persists_confirmation_without_exposing_full_content(tmp_path):
    class ConfirmationAgent:
        def __init__(self, memory):
            self.memory = memory

        def handle(self, content):
            return {
                "ok": False,
                "status": "waiting_confirmation",
                "message": "Preciso de confirmacao.",
                "suggestions": [],
                "confirmation": {
                    "capability": "create_file",
                    "arguments": {
                        "path": "C:\\Users\\user\\receita.md",
                        "content": "conteudo privado muito longo",
                    },
                },
            }

    class ConfirmationFactory:
        def build_agent(self, memory=None, confirmer=None):
            return ConfirmationAgent(memory or SessionMemory())

    repository = SessionRepository(tmp_path / "argos.db")
    service = GatewayService(ConfirmationFactory(), repository)

    response = service.handle(
        AgentRequest(session_id="default", content="crie a receita")
    )
    stored = repository.load_confirmation(
        response.confirmation.confirmation_id
    )

    assert response.status == "waiting_confirmation"
    assert response.confirmation.arguments_summary["path"].endswith("receita.md")
    assert response.confirmation.arguments_summary["content_length"] == 28
    assert "conteudo privado muito longo" not in str(
        response.confirmation.arguments_summary
    )
    assert stored["arguments"]["content"] == "conteudo privado muito longo"
    repository.close()


def test_service_starts_capability_graph_and_returns_pending_approval(
    tmp_path,
):
    class GapAgent:
        def __init__(self, memory):
            self.memory = memory

        def handle(self, content):
            return {
                "ok": False,
                "status": "waiting_confirmation",
                "message": "gap",
                "suggestions": [],
                "error_code": "capability_gap",
                "confirmation": {
                    "capability": "tool.provision_draft",
                    "arguments": {
                        "proposal_id": "proposal-1",
                        "status": "proposed",
                        "requested_capability": "file.metadata.stat",
                        "user_goal": content,
                        "arguments": {"path": "notes.txt"},
                        "platform_context": {},
                        "original_action": {
                            "mode": "action",
                            "capability": "file.metadata.stat",
                            "arguments": {"path": "notes.txt"},
                        },
                        "definition": {
                            "name": "file.metadata.stat",
                            "version": "1.0.0",
                            "title": "File Metadata",
                            "description": "Read metadata.",
                            "input_schema": {
                                "type": "object",
                                "properties": {"path": {"type": "string"}},
                            },
                            "output_schema": {"type": "object"},
                            "permissions": {
                                "filesystem": {
                                    "read": ["${path}"],
                                    "write": [],
                                },
                                "network": {
                                    "enabled": False,
                                    "hosts": [],
                                },
                                "subprocess": {"executables": []},
                            },
                            "execution": {
                                "timeout_seconds": 10,
                                "max_output_bytes": 16384,
                            },
                            "handler_body": (
                                "def run(arguments):\n"
                                "    return {'path': arguments['path']}\n"
                            ),
                        },
                        "tool_definition_hash": "hash-1",
                        "reason": None,
                    },
                },
            }

    class FakeGraph:
        def __init__(self):
            self.started = []

        def start_from_proposal(self, **kwargs):
            self.started.append(kwargs)
            return {
                "ok": True,
                "result": "pending_approval",
                "status": "WAITING_TOOL_APPROVAL",
                "workflow_id": "workflow-1",
                "message": "Draft validado.",
                "approval": {
                    "tool_name": "file.metadata.stat",
                    "version": "1.0.0",
                },
                "error_code": None,
            }

    class GraphFactory:
        def __init__(self):
            self.graph = FakeGraph()

        def build_agent(self, memory=None, confirmer=None):
            return GapAgent(memory or SessionMemory())

        def build_capability_graph(self, **_kwargs):
            return self.graph

    repository = SessionRepository(tmp_path / "argos.db")
    factory = GraphFactory()
    service = GatewayService(factory, repository)

    response = service.handle(
        AgentRequest(
            session_id="s1",
            run_id="run-1",
            content="data de criacao de notes.txt",
        )
    )

    assert response.ok is True
    assert response.status == "pending_approval"
    assert response.result == "pending_approval"
    assert response.workflow_id == "workflow-1"
    assert len(factory.graph.started) == 1
    repository.close()


def test_service_routes_explicit_workflow_decisions(tmp_path):
    class FakeGraph:
        def decide_tool(self, workflow_id, decision):
            assert (workflow_id, decision) == (
                "workflow-1",
                "approve_enable_only",
            )
            return {
                "ok": True,
                "result": "pending_confirmation",
                "status": "WAITING_RETRY_CONFIRMATION",
                "workflow_id": workflow_id,
                "message": "Confirme o retry.",
                "error_code": None,
            }

    class GraphFactory(FakeRuntimeFactory):
        def build_capability_graph(self, **_kwargs):
            return FakeGraph()

    repository = SessionRepository(tmp_path / "argos.db")
    service = GatewayService(GraphFactory(), repository)

    response = service.resolve_capability_tool_decision(
        "workflow-1",
        "approve_enable_only",
    )

    assert response.status == "pending_confirmation"
    assert response.workflow_status == "WAITING_RETRY_CONFIRMATION"
    repository.close()


def test_service_summarizes_tool_draft_confirmation(tmp_path):
    class ProvisioningAgent:
        def __init__(self, memory):
            self.memory = memory

        def handle(self, content):
            return {
                "ok": False,
                "status": "waiting_confirmation",
                "message": "Posso criar uma tool local em draft?",
                "suggestions": [],
                "error_code": "capability_gap",
                "confirmation": {
                    "capability": "tool.provision_draft",
                    "arguments": {
                        "proposal_id": "proposal-1",
                        "status": "proposed",
                        "requested_capability": "shell.run",
                        "user_goal": content,
                        "arguments": {"command": "git status"},
                        "platform_context": {},
                        "original_action": {},
                        "reason": None,
                        "definition": {
                            "name": "local.git.status",
                            "version": "1.0.0",
                            "title": "Git Status",
                            "description": "Executa git status.",
                            "input_schema": {},
                            "output_schema": {},
                            "permissions": {},
                            "execution": {},
                            "handler_body": "conteudo interno sensivel",
                        },
                    },
                },
            }

    class ProvisioningFactory:
        def build_agent(self, memory=None, confirmer=None):
            return ProvisioningAgent(memory or SessionMemory())

    repository = SessionRepository(tmp_path / "argos.db")
    service = GatewayService(ProvisioningFactory(), repository)

    response = service.handle(
        AgentRequest(session_id="default", content="rode git status")
    )

    assert response.confirmation.question == (
        "Criar a tool local em draft para revisao?"
    )
    assert response.confirmation.arguments_summary == {
        "requested_capability": "shell.run",
        "tool_name": "local.git.status",
        "tool_version": "1.0.0",
    }
    assert response.confirmation.permissions == [
        "create:local_tool_draft",
        "execute:none",
    ]
    assert "conteudo interno sensivel" not in str(
        response.confirmation.arguments_summary
    )
    repository.close()


def test_service_resumes_approved_confirmation_after_restart(tmp_path):
    class ConfirmationAgent:
        def __init__(self, memory):
            self.memory = memory

        def handle(self, content):
            return {
                "ok": False,
                "status": "waiting_confirmation",
                "message": "Preciso de confirmacao.",
                "suggestions": [],
                "confirmation": {
                    "capability": "create_file",
                    "arguments": {"path": "C:\\Users\\user\\receita.md"},
                },
            }

        def execute_confirmed_action(self, capability, arguments, approved):
            return {
                "ok": approved,
                "status": "completed",
                "message": "Arquivo criado" if approved else "Acao rejeitada",
                "suggestions": [],
            }

    class ConfirmationFactory:
        def build_agent(self, memory=None, confirmer=None):
            return ConfirmationAgent(memory or SessionMemory())

    repository = SessionRepository(tmp_path / "argos.db")
    first = GatewayService(ConfirmationFactory(), repository)
    pending = first.handle(
        AgentRequest(session_id="default", content="crie o arquivo")
    )

    restarted = GatewayService(ConfirmationFactory(), repository)
    result = restarted.resolve_confirmation(
        pending.confirmation.confirmation_id,
        approved=True,
    )

    assert result.ok is True
    assert result.message == "Arquivo criado"
    assert (
        repository.load_confirmation(
            pending.confirmation.confirmation_id
        )["status"]
        == "approved"
    )
    repository.close()


def test_service_maps_predictable_confirmation_failure(tmp_path):
    class PermissionDeniedAgent:
        def __init__(self, memory):
            self.memory = memory

        def handle(self, content):
            return {
                "ok": False,
                "status": "waiting_confirmation",
                "message": "Preciso de confirmacao.",
                "suggestions": [],
                "confirmation": {
                    "capability": "file.write",
                    "arguments": {
                        "path": "C:\\restricted.txt",
                        "content": "x",
                        "mode": "overwrite",
                    },
                },
            }

        def execute_confirmed_action(self, capability, arguments, approved):
            raise PermissionError("access denied")

    class PermissionDeniedFactory:
        def build_agent(self, memory=None, confirmer=None):
            return PermissionDeniedAgent(memory or SessionMemory())

    repository = SessionRepository(tmp_path / "argos.db")
    service = GatewayService(PermissionDeniedFactory(), repository)
    pending = service.handle(
        AgentRequest(session_id="default", content="escreva")
    )

    result = service.resolve_confirmation(
        pending.confirmation.confirmation_id,
        approved=True,
    )

    assert result.ok is False
    assert result.status == "error"
    assert result.error_code == "permission_denied"
    repository.close()


def test_service_reloads_session_agent_and_persists_retry_confirmation(
    tmp_path,
):
    class LifecycleAgent:
        def __init__(self, memory, generation):
            self.memory = memory
            self.generation = generation
            self.reload_recorded = False

        def handle(self, content):
            return {
                "ok": False,
                "status": "waiting_confirmation",
                "message": "Aprovar tool?",
                "suggestions": [],
                "confirmation": {
                    "capability": "tool.approve_install_enable",
                    "arguments": {"draft_path": "draft"},
                },
            }

        def execute_confirmed_action(
            self,
            capability,
            arguments,
            approved,
        ):
            assert self.generation == 1
            return {
                "ok": True,
                "status": "registry_reload_required",
                "message": "Tool habilitada.",
                "suggestions": [],
                "reload": {
                    "proposal_id": "proposal-1",
                    "tool_name": "local.windows.env_set_user",
                    "tool_version": "1.0.0",
                    "state": "enabled",
                    "installed_path": "tools/local.windows.env_set_user/1.0.0",
                    "original_action": {
                        "mode": "action",
                        "capability": "modify_environment_variable",
                        "arguments": {"name": "TESTE", "value": "456"},
                    },
                },
            }

        def record_registry_reload(self, payload):
            assert self.generation == 2
            self.reload_recorded = True

        def prepare_provisioned_retry(self, payload):
            assert self.generation == 2
            assert self.reload_recorded is True
            return {
                "ok": False,
                "status": "waiting_confirmation",
                "message": "Confirmar retry?",
                "suggestions": [],
                "confirmation": {
                    "capability": "local.windows.env_set_user",
                    "arguments": {"name": "TESTE", "value": "456"},
                    "dry_run": {
                        "action": "local.windows.env_set_user",
                    },
                },
            }

    class LifecycleFactory:
        def __init__(self):
            self.build_count = 0

        def build_agent(self, memory=None, confirmer=None):
            self.build_count += 1
            return LifecycleAgent(
                memory or SessionMemory(),
                self.build_count,
            )

    repository = SessionRepository(tmp_path / "argos.db")
    factory = LifecycleFactory()
    service = GatewayService(factory, repository)
    pending = service.handle(
        AgentRequest(session_id="default", content="habilite a tool")
    )

    result = service.resolve_confirmation(
        pending.confirmation.confirmation_id,
        approved=True,
    )

    assert factory.build_count == 2
    assert result.status == "waiting_confirmation"
    assert result.confirmation.capability == (
        "local.windows.env_set_user"
    )
    stored = repository.load_confirmation(
        result.confirmation.confirmation_id
    )
    assert stored["arguments"] == {"name": "TESTE", "value": "456"}
    repository.close()
