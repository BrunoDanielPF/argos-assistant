import httpx
import pytest

from assistant.config import AppConfig
from assistant.gateway.client import (
    GatewayAuthenticationError,
    GatewayClient,
    GatewayProtocolError,
    GatewayUnavailable,
)


def build_config(tmp_path):
    token_file = tmp_path / "gateway.token"
    token_file.write_text("local-token", encoding="ascii")
    return AppConfig(gateway_token_file=token_file)


def test_client_sends_token_and_contract(tmp_path):
    config = build_config(tmp_path)

    def handler(request):
        assert request.headers["Authorization"] == "Bearer local-token"
        assert request.url.path == "/v1/chat"
        return httpx.Response(
            200,
            json={
                "session_id": "default",
                "run_id": "r1",
                "ok": True,
                "message": "ola",
                "suggestions": [],
            },
        )

    response = GatewayClient(
        config,
        transport=httpx.MockTransport(handler),
    ).chat("default", "oi")

    assert response.message == "ola"


def test_client_maps_connection_failure(tmp_path):
    config = build_config(tmp_path)

    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    client = GatewayClient(config, transport=httpx.MockTransport(handler))

    with pytest.raises(GatewayUnavailable):
        client.status()


def test_client_maps_authentication_failure(tmp_path):
    config = build_config(tmp_path)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, json={"detail": "invalid"})
    )

    with pytest.raises(GatewayAuthenticationError):
        GatewayClient(config, transport=transport).status()


def test_client_rejects_invalid_chat_contract(tmp_path):
    config = build_config(tmp_path)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"ok": True})
    )

    with pytest.raises(GatewayProtocolError):
        GatewayClient(config, transport=transport).chat("default", "oi")


def test_client_loads_persisted_session_snapshot(tmp_path):
    config = build_config(tmp_path)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "history": [{"role": "user", "content": "oi"}],
                "audit": [],
                "suggestions": [],
                "context": {"current_cwd": "C:\\workspace"},
            },
        )
    )

    snapshot = GatewayClient(
        config,
        transport=transport,
    ).get_session("default")

    assert snapshot["history"][0]["content"] == "oi"


def test_client_sends_confirmation_decision(tmp_path):
    config = build_config(tmp_path)

    def handler(request):
        assert request.url.path == "/v1/confirmations/confirm-1"
        assert request.read().decode() == '{"approved":true}'
        return httpx.Response(
            200,
            json={
                "session_id": "default",
                "run_id": "run-1",
                "ok": True,
                "status": "completed",
                "message": "Arquivo criado",
                "suggestions": [],
                "confirmation": None,
            },
        )

    response = GatewayClient(
        config,
        transport=httpx.MockTransport(handler),
    ).confirm("confirm-1", approved=True)

    assert response.ok is True
