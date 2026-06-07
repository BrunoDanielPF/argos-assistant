import pytest
from pydantic import ValidationError

from assistant.runtime.contracts import (
    AgentRequest,
    AgentResponse,
    ConfirmationRequest,
)


def test_request_generates_run_id_and_keeps_session():
    request = AgentRequest(session_id="default", content="oi")

    assert request.session_id == "default"
    assert request.run_id


def test_response_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        AgentResponse(
            session_id="default",
            run_id="run-1",
            ok=True,
            message="ola",
            suggestions=[],
            unexpected=True,
        )


def test_response_can_require_confirmation():
    confirmation = ConfirmationRequest(
        confirmation_id="confirm-1",
        capability="write_file",
        arguments_summary={"path": "C:\\Users\\user\\receita.md"},
        permissions=["write:C:\\Users\\user\\receita.md"],
        question="Autorizar escrita do arquivo?",
    )

    response = AgentResponse(
        session_id="default",
        run_id="run-1",
        ok=False,
        status="waiting_confirmation",
        message="Confirmacao necessaria.",
        confirmation=confirmation,
    )

    assert response.confirmation.capability == "write_file"
