from copy import deepcopy

import pytest

from assistant.capabilities.definitions import ToolDefinition
from assistant.capabilities.generated_tool_policy import (
    GeneratedToolSafetyPolicy,
)

from tests.capabilities.test_model_definition_source import (
    metadata_definition,
)


def evaluate(payload: dict):
    return GeneratedToolSafetyPolicy().evaluate(
        ToolDefinition.model_validate(payload)
    )


def test_read_only_file_metadata_definition_is_allowed():
    decision = evaluate(metadata_definition())

    assert decision.allowed is True
    assert decision.reasons == []


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda payload: payload["permissions"]["filesystem"]["write"].append(
                "${path}"
            ),
            "filesystem_write_not_allowed",
        ),
        (
            lambda payload: payload["permissions"]["network"].update(
                {"enabled": True, "hosts": ["example.com"]}
            ),
            "network_not_allowed",
        ),
        (
            lambda payload: payload["permissions"]["subprocess"][
                "executables"
            ].append("git"),
            "subprocess_not_allowed",
        ),
    ],
)
def test_effectful_model_definition_is_blocked(mutate, reason):
    payload = deepcopy(metadata_definition())
    mutate(payload)

    decision = evaluate(payload)

    assert decision.allowed is False
    assert reason in decision.reasons


def test_unknown_ast_call_is_blocked_fail_closed():
    payload = deepcopy(metadata_definition())
    payload["handler_body"] = (
        "def run(arguments):\n"
        "    return mystery(arguments['path'])\n"
    )

    decision = evaluate(payload)

    assert decision.allowed is False
    assert "unknown_call:mystery" in decision.reasons


def test_top_level_effect_is_blocked():
    payload = deepcopy(metadata_definition())
    payload["handler_body"] = (
        "import os\n"
        "metadata = os.stat('notes.txt')\n\n"
        "def run(arguments):\n"
        "    return {'path': arguments['path']}\n"
    )

    decision = evaluate(payload)

    assert decision.allowed is False
    assert "top_level_effect" in decision.reasons


def test_environment_assignment_is_blocked():
    payload = deepcopy(metadata_definition())
    payload["handler_body"] = (
        "import os\n\n"
        "def run(arguments):\n"
        "    os.environ['ARGOS_TEST'] = 'unsafe'\n"
        "    return {'path': arguments['path']}\n"
    )

    decision = evaluate(payload)

    assert decision.allowed is False
    assert "external_assignment" in decision.reasons


def test_literal_filesystem_read_permission_is_blocked():
    payload = deepcopy(metadata_definition())
    payload["permissions"]["filesystem"]["read"] = ["C:/Users/**"]

    decision = evaluate(payload)

    assert decision.allowed is False
    assert "filesystem_read_must_use_input_placeholder" in decision.reasons
