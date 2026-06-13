from contextlib import asynccontextmanager
from time import monotonic

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from assistant.gateway.auth import LocalTokenStore
from assistant.runtime.contracts import (
    AgentRequest,
    AgentResponse,
    CapabilityRetryDecision,
    CapabilityToolDecision,
    ConfirmationDecision,
)
from assistant.sessions.repository import SessionRepository


def create_gateway_app(
    service,
    token_store: LocalTokenStore,
    repository: SessionRepository,
    model_name: str,
    scheduler=None,
    version: str = "0.1.0",
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if scheduler is not None:
            scheduler.start()
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.stop()

    app = FastAPI(title="Argos Gateway", version=version, lifespan=lifespan)
    started_at = monotonic()

    def authenticate(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")
        candidate = authorization.removeprefix("Bearer ").strip()
        if not candidate or not token_store.verify(candidate):
            raise HTTPException(status_code=401, detail="Invalid token")

    @app.get("/v1/health", dependencies=[Depends(authenticate)])
    def health() -> dict:
        return {"status": "ok", "version": version}

    @app.get("/v1/status", dependencies=[Depends(authenticate)])
    def status() -> dict:
        return {
            "status": "ok",
            "version": version,
            "model": model_name,
            "uptime_seconds": max(0.0, monotonic() - started_at),
            "jobs_scheduler": "enabled" if scheduler is not None else "disabled",
        }

    @app.post(
        "/v1/chat",
        response_model=AgentResponse,
        dependencies=[Depends(authenticate)],
    )
    def chat(request: AgentRequest):
        try:
            return service.handle(request)
        except Exception:
            return JSONResponse(
                status_code=500,
                content={
                    "message": "Internal gateway error",
                    "run_id": request.run_id,
                },
            )

    @app.post(
        "/v1/confirmations/{confirmation_id}",
        response_model=AgentResponse,
        dependencies=[Depends(authenticate)],
    )
    def resolve_confirmation(
        confirmation_id: str,
        decision: ConfirmationDecision,
    ):
        try:
            return service.resolve_confirmation(
                confirmation_id,
                approved=decision.approved,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail="Confirmation not found or already resolved",
            ) from exc

    @app.get(
        "/v1/capability-workflows",
        dependencies=[Depends(authenticate)],
    )
    def capability_workflows(session_id: str | None = None) -> dict:
        return {
            "workflows": service.list_capability_workflows(session_id)
        }

    @app.post(
        "/v1/capability-workflows/{workflow_id}/tool-decision",
        response_model=AgentResponse,
        dependencies=[Depends(authenticate)],
    )
    def resolve_tool_decision(
        workflow_id: str,
        decision: CapabilityToolDecision,
    ):
        try:
            return service.resolve_capability_tool_decision(
                workflow_id,
                decision.decision,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/v1/capability-workflows/{workflow_id}/retry-decision",
        response_model=AgentResponse,
        dependencies=[Depends(authenticate)],
    )
    def resolve_retry_decision(
        workflow_id: str,
        decision: CapabilityRetryDecision,
    ):
        try:
            return service.resolve_capability_retry_decision(
                workflow_id,
                decision.decision,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete(
        "/v1/capability-workflows/{workflow_id}",
        response_model=AgentResponse,
        dependencies=[Depends(authenticate)],
    )
    def cancel_capability_workflow(workflow_id: str):
        try:
            return service.cancel_capability_workflow(workflow_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/sessions", dependencies=[Depends(authenticate)])
    def sessions() -> dict:
        return {"sessions": repository.list_sessions()}

    @app.get(
        "/v1/sessions/{session_id}",
        dependencies=[Depends(authenticate)],
    )
    def session(session_id: str) -> dict:
        snapshot = repository.load(session_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return snapshot

    return app
