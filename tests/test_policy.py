from assistant.execution.policy import decide_policy


def test_policy_blocks_shell_command_when_runtime_has_no_shell_executor():
    decision = decide_policy("run_shell_command")
    assert decision == "blocked"


def test_policy_requires_confirmation_for_create_file():
    assert decide_policy("create_file") == "confirm"


def test_policy_requires_confirmation_for_write_file():
    assert decide_policy("write_file") == "confirm"


def test_policy_requires_confirmation_for_schedule_reminder():
    assert decide_policy("schedule_reminder") == "confirm"


def test_policy_blocks_unknown_capability():
    assert decide_policy("clarification") == "blocked"
