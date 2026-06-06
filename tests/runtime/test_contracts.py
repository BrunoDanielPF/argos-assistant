import pytest
from pydantic import ValidationError

from assistant.runtime.contracts import AgentRequest, AgentResponse


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
