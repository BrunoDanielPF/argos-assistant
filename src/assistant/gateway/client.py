from typing import Any

import httpx
from pydantic import ValidationError

from assistant.config import AppConfig
from assistant.runtime.contracts import AgentRequest, AgentResponse


class GatewayError(RuntimeError):
    pass


class GatewayUnavailable(GatewayError):
    pass


class GatewayAuthenticationError(GatewayError):
    pass


class GatewayProtocolError(GatewayError):
    pass


class GatewayClient:
    def __init__(
        self,
        config: AppConfig,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._base_url = (
            f"http://{config.gateway_host}:{config.gateway_port}"
        )

    def chat(
        self,
        session_id: str,
        content: str,
        cwd: str | None = None,
    ) -> AgentResponse:
        request = AgentRequest(
            session_id=session_id,
            content=content,
            cwd=cwd,
        )
        payload = self._request(
            "POST",
            "/v1/chat",
            json=request.model_dump(exclude_none=True),
        )
        try:
            return AgentResponse.model_validate(payload)
        except ValidationError as exc:
            raise GatewayProtocolError("Invalid gateway chat response") from exc

    def health(self) -> dict:
        return self._request("GET", "/v1/health")

    def status(self) -> dict:
        return self._request("GET", "/v1/status")

    def list_sessions(self) -> list[dict]:
        payload = self._request("GET", "/v1/sessions")
        sessions = payload.get("sessions")
        if not isinstance(sessions, list):
            raise GatewayProtocolError("Invalid sessions response")
        return sessions

    def get_session(self, session_id: str) -> dict:
        payload = self._request("GET", f"/v1/sessions/{session_id}")
        required = {"history", "audit", "suggestions", "context"}
        if not required.issubset(payload):
            raise GatewayProtocolError("Invalid session snapshot")
        return payload

    def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
    ) -> dict[str, Any]:
        token = self._read_token()
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=httpx.Timeout(
                    connect=2.0,
                    read=120.0,
                    write=10.0,
                    pool=2.0,
                ),
                transport=self._transport,
            ) as client:
                response = client.request(
                    method,
                    path,
                    headers={"Authorization": f"Bearer {token}"},
                    json=json,
                )
        except httpx.RequestError as exc:
            raise GatewayUnavailable(
                f"Argos gateway is unavailable at {self._base_url}"
            ) from exc

        if response.status_code == 401:
            raise GatewayAuthenticationError("Gateway authentication failed")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GatewayProtocolError(
                f"Gateway returned HTTP {response.status_code}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise GatewayProtocolError("Gateway returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise GatewayProtocolError("Gateway returned a non-object response")
        return payload

    def _read_token(self) -> str:
        try:
            token = self._config.gateway_token_file.read_text(
                encoding="ascii"
            ).strip()
        except OSError as exc:
            raise GatewayUnavailable(
                "Gateway token is unavailable; start Argos first"
            ) from exc
        if not token:
            raise GatewayProtocolError("Gateway token file is empty")
        return token
