from fastapi.testclient import TestClient

from assistant.gateway.app import create_gateway_app
from assistant.gateway.auth import LocalTokenStore
from assistant.runtime.contracts import AgentResponse
from assistant.sessions.repository import SessionRepository


class FakeGatewayService:
    def handle(self, request):
        return AgentResponse(
            session_id=request.session_id,
            run_id=request.run_id,
            ok=True,
            message=f"handled {request.content}",
            suggestions=[],
        )


def build_client(tmp_path):
    token_store = LocalTokenStore(
        tmp_path / "gateway.token",
        permission_hardener=lambda path: None,
    )
    token = token_store.get_or_create()
    repository = SessionRepository(tmp_path / "argos.db")
    app = create_gateway_app(
        service=FakeGatewayService(),
        token_store=token_store,
        repository=repository,
        model_name="test-model",
    )
    return TestClient(app, raise_server_exceptions=False), token, repository


def test_health_is_available_with_valid_token(tmp_path):
    client, token, repository = build_client(tmp_path)

    response = client.get(
        "/v1/health",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    repository.close()


def test_chat_rejects_missing_token(tmp_path):
    client, _, repository = build_client(tmp_path)

    response = client.post(
        "/v1/chat",
        json={"session_id": "default", "content": "oi"},
    )

    assert response.status_code == 401
    repository.close()


def test_chat_returns_runtime_contract(tmp_path):
    client, token, repository = build_client(tmp_path)

    response = client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_id": "default", "content": "oi"},
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "default"
    assert response.json()["message"] == "handled oi"
    assert response.json()["run_id"]
    repository.close()


def test_sessions_endpoints_list_and_load_snapshots(tmp_path):
    client, token, repository = build_client(tmp_path)
    repository.save(
        "default",
        {
            "history": [{"role": "user", "content": "oi"}],
            "audit": [],
            "suggestions": [],
            "context": {},
        },
    )
    headers = {"Authorization": f"Bearer {token}"}

    listed = client.get("/v1/sessions", headers=headers)
    loaded = client.get("/v1/sessions/default", headers=headers)

    assert listed.json()["sessions"][0]["session_id"] == "default"
    assert loaded.json()["history"][0]["content"] == "oi"
    repository.close()


def test_internal_error_returns_safe_message_and_run_id(tmp_path):
    class FailingService:
        def handle(self, request):
            raise RuntimeError("private stack detail")

    token_store = LocalTokenStore(
        tmp_path / "gateway.token",
        permission_hardener=lambda path: None,
    )
    token = token_store.get_or_create()
    repository = SessionRepository(tmp_path / "argos.db")
    client = TestClient(
        create_gateway_app(
            service=FailingService(),
            token_store=token_store,
            repository=repository,
            model_name="test-model",
        ),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_id": "default", "content": "oi"},
    )

    assert response.status_code == 500
    assert response.json()["message"] == "Internal gateway error"
    assert response.json()["run_id"]
    assert "private stack detail" not in response.text
    repository.close()
