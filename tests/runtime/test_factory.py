from assistant.config import AppConfig
from assistant.memory.session import SessionMemory
from assistant.runtime.factory import RuntimeFactory
from assistant.capabilities.model_definition_source import (
    ModelBackedToolDefinitionSource,
)


def test_factory_builds_agent_with_provided_memory(monkeypatch, tmp_path):
    class FakeCatalog:
        def list_enabled(self):
            return []

        def get_enabled(self, capability):
            return None

    class FakeRegistry:
        def list_all(self):
            return []

    class FakeExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def configure_tools(self, catalog, runner):
            self.catalog = catalog
            self.runner = runner

    class FakePlanner:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(
        "assistant.runtime.factory.RuntimeFactory.build_tool_catalog",
        lambda self: FakeCatalog(),
    )
    monkeypatch.setattr(
        "assistant.runtime.factory.build_default_registry",
        lambda catalog: FakeRegistry(),
    )
    monkeypatch.setattr("assistant.runtime.factory.OllamaClient", lambda **kwargs: object())
    monkeypatch.setattr("assistant.runtime.factory.Planner", FakePlanner)
    monkeypatch.setattr("assistant.runtime.factory.ActionExecutor", FakeExecutor)

    memory = SessionMemory()
    config = AppConfig(
        memory_dir=tmp_path / "memory",
        tool_audit_file=tmp_path / "audit.jsonl",
    )

    agent = RuntimeFactory(config=config).build_agent(memory=memory)

    assert agent.memory is memory
    assert agent._recovery_engine is not None
    assert agent._capability_provisioning_service is not None
    assert any(
        isinstance(source, ModelBackedToolDefinitionSource)
        for source in agent._capability_provisioning_service._definition_sources
    )


def test_factory_injects_provided_memory_engine(monkeypatch, tmp_path):
    class FakeCatalog:
        def list_enabled(self):
            return []

        def get_enabled(self, capability):
            return None

    class FakeRegistry:
        def list_all(self):
            return []

    class FakeExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def configure_tools(self, catalog, runner):
            pass

    memory_engine = object()
    monkeypatch.setattr(
        "assistant.runtime.factory.RuntimeFactory.build_tool_catalog",
        lambda self: FakeCatalog(),
    )
    monkeypatch.setattr(
        "assistant.runtime.factory.build_default_registry",
        lambda catalog: FakeRegistry(),
    )
    monkeypatch.setattr("assistant.runtime.factory.OllamaClient", lambda **kwargs: object())
    monkeypatch.setattr(
        "assistant.runtime.factory.Planner",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr("assistant.runtime.factory.ActionExecutor", FakeExecutor)

    config = AppConfig(
        database_file=tmp_path / "argos.db",
        memory_dir=tmp_path / "memory",
        tool_audit_file=tmp_path / "audit.jsonl",
    )
    agent = RuntimeFactory(
        config=config,
        memory_engine=memory_engine,
    ).build_agent()

    assert agent._memory_engine is memory_engine


def test_factory_preserves_restored_session_context(monkeypatch, tmp_path):
    class FakeCatalog:
        def list_enabled(self):
            return []

        def get_enabled(self, capability):
            return None

    class FakeRegistry:
        def list_all(self):
            return []

    class FakeExecutor:
        def __init__(self, *args, **kwargs):
            pass

        def configure_tools(self, catalog, runner):
            pass

    monkeypatch.setattr(
        "assistant.runtime.factory.RuntimeFactory.build_tool_catalog",
        lambda self: FakeCatalog(),
    )
    monkeypatch.setattr(
        "assistant.runtime.factory.build_default_registry",
        lambda catalog: FakeRegistry(),
    )
    monkeypatch.setattr("assistant.runtime.factory.OllamaClient", lambda **kwargs: object())
    monkeypatch.setattr(
        "assistant.runtime.factory.Planner",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr("assistant.runtime.factory.ActionExecutor", FakeExecutor)

    memory = SessionMemory()
    memory.set_context(
        current_cwd="C:\\restored",
        default_search_root="C:\\restored",
        user_home="C:\\Users\\restored",
    )
    config = AppConfig(
        memory_dir=tmp_path / "memory",
        tool_audit_file=tmp_path / "audit.jsonl",
    )

    agent = RuntimeFactory(config=config).build_agent(memory=memory)

    assert agent.memory.snapshot()["context"]["current_cwd"] == "C:\\restored"


def test_factory_builds_durable_capability_graph(tmp_path):
    config = AppConfig(
        argos_home=tmp_path,
        database_file=tmp_path / "argos.db",
        capability_checkpoint_file=tmp_path / "checkpoints.db",
        memory_dir=tmp_path / "memory",
        tool_audit_file=tmp_path / "audit.jsonl",
    )
    factory = RuntimeFactory(config=config, memory_engine=object())

    graph = factory.build_capability_graph(
        reload_session=lambda _session_id: None,
        execute_action=lambda _session_id, _action: {"ok": True},
        audit=lambda _event, _details: None,
    )

    assert graph is not None
    assert config.capability_checkpoint_file.exists()
