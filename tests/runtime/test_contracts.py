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


def test_confirmation_can_include_dry_run():
    confirmation = ConfirmationRequest(
        confirmation_id="confirm-1",
        capability="create_file",
        arguments_summary={"path": "C:\\notes.md"},
        permissions=["write:C:\\notes.md"],
        question="Autorizar?",
        dry_run={
            "action": "create_file",
            "resources_affected": ["C:\\notes.md"],
            "risk": "medium",
            "permissions_required": ["write:C:\\notes.md"],
            "requires_confirmation": True,
            "expected_result": "Arquivo seria criado.",
            "can_execute": True,
        },
    )

    assert confirmation.dry_run["action"] == "create_file"
