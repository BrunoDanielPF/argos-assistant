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
