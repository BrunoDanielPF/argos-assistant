import json

from assistant.config import AppConfig
from assistant.gateway.service import GatewayService
from assistant.runtime.contracts import AgentRequest
from assistant.runtime.factory import RuntimeFactory
from assistant.sessions.repository import SessionRepository
from assistant.tools.runner import ToolRunResult

from tests.capabilities.test_model_definition_source import metadata_definition


class MetadataModelClient:
    def chat(self, _messages):
        raise AssertionError("metadata request should use deterministic planning")

    def chat_structured(self, _messages, _schema):
        return {"response": json.dumps(metadata_definition())}


def test_metadata_gap_draft_enable_reload_run_once_and_reuse(
    monkeypatch,
    tmp_path,
):
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    config = AppConfig(
        argos_home=tmp_path,
        database_file=tmp_path / "argos.db",
        capability_checkpoint_file=tmp_path / "checkpoints.db",
        memory_dir=tmp_path / "memory",
        tools_dir=tmp_path / "tools",
        tool_drafts_dir=tmp_path / "tool-drafts",
        tool_envs_dir=tmp_path / "tool-envs",
        tool_state_file=tmp_path / "tool-state.json",
        tool_audit_file=tmp_path / "tool-audit.jsonl",
        recovery_audit_file=tmp_path / "recovery.jsonl",
    )
    monkeypatch.setattr(
        RuntimeFactory,
        "_build_ollama_client",
        lambda self: MetadataModelClient(),
    )
    repository = SessionRepository(config.database_file)
    service = GatewayService(
        RuntimeFactory(config, memory_engine=object()),
        repository,
    )

    pending = service.handle(
        AgentRequest(
            session_id="s1",
            run_id="run-1",
            cwd=str(tmp_path),
            content=(
                "quero que me diga a data de criação do arquivo notes.txt"
            ),
        )
    )

    assert pending.ok is True
    assert pending.status == "pending_approval"
    assert pending.error_code is None
    assert pending.approval["tool_name"] == "file.metadata.stat"

    executed = service.resolve_capability_tool_decision(
        pending.workflow_id,
        "approve_enable_and_run_once",
    )

    assert executed.ok is True
    assert executed.status == "success"
    assert executed.execution_result["ok"] is True

    reused = service.handle(
        AgentRequest(
            session_id="s1",
            run_id="run-2",
            cwd=str(tmp_path),
            content="qual a data de criacao do arquivo notes.txt",
        )
    )

    assert reused.ok is True
    assert reused.status == "completed"
    assert "pending_approval" not in reused.model_dump_json()
    repository.close()


def test_environment_gap_enable_reload_and_confirmed_retry_uses_fake_runner(
    monkeypatch,
    tmp_path,
):
    calls = []

    class DeterministicClient:
        def chat(self, _messages):
            raise AssertionError("environment request should be deterministic")

        def chat_structured(self, _messages, _schema):
            raise AssertionError("safe environment template should be used")

    class FakeRunner:
        def __init__(self, audit_log=None):
            self.audit_log = audit_log

        def run(self, tool, arguments):
            calls.append((tool.manifest.name, dict(arguments)))
            return ToolRunResult(ok=True, result={"updated": True})

    config = AppConfig(
        argos_home=tmp_path,
        database_file=tmp_path / "argos.db",
        capability_checkpoint_file=tmp_path / "checkpoints.db",
        memory_dir=tmp_path / "memory",
        tools_dir=tmp_path / "tools",
        tool_drafts_dir=tmp_path / "tool-drafts",
        tool_envs_dir=tmp_path / "tool-envs",
        tool_state_file=tmp_path / "tool-state.json",
        tool_audit_file=tmp_path / "tool-audit.jsonl",
        recovery_audit_file=tmp_path / "recovery.jsonl",
    )
    monkeypatch.setattr(
        RuntimeFactory,
        "_build_ollama_client",
        lambda self: DeterministicClient(),
    )
    monkeypatch.setattr("assistant.runtime.factory.ToolRunner", FakeRunner)
    repository = SessionRepository(config.database_file)
    service = GatewayService(
        RuntimeFactory(config, memory_engine=object()),
        repository,
    )

    pending = service.handle(
        AgentRequest(
            session_id="s1",
            run_id="run-env-1",
            cwd=str(tmp_path),
            content=(
                "configure uma variável de ambiente chamada "
                "ARGOS_TESTE_NOVA com valor 456"
            ),
        )
    )

    assert pending.status == "pending_approval"
    assert "approve_enable_and_run_once" not in pending.approval["options"]

    retry = service.resolve_capability_tool_decision(
        pending.workflow_id,
        "approve_enable_only",
    )
    assert retry.status == "pending_confirmation"
    assert calls == []

    executed = service.resolve_capability_retry_decision(
        pending.workflow_id,
        "confirm",
    )

    assert executed.status == "success"
    assert calls == [
        (
            "local.windows.env_set_user",
            {"name": "ARGOS_TESTE_NOVA", "value": "456"},
        )
    ]
    assert all(capability != "file.write" for capability, _ in calls)
    repository.close()
