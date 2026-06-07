from fastapi.testclient import TestClient

from assistant.gateway.app import create_gateway_app
from assistant.gateway.auth import LocalTokenStore
from assistant.gateway.service import GatewayService
from assistant.agent import AssistantAgent
from assistant.execution.executor import ActionExecutor
from assistant.memory.session import SessionMemory
from assistant.runtime.contracts import AgentRequest
from assistant.sessions.repository import SessionRepository


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
