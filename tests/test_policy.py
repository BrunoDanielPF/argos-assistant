from assistant.execution.policy import decide_policy


def test_policy_requires_confirmation_for_shell_command():
    decision = decide_policy("run_shell_command")
    assert decision == "confirm"


def test_policy_requires_confirmation_for_create_file():
    assert decide_policy("create_file") == "confirm"


def test_policy_requires_confirmation_for_write_file():
    assert decide_policy("write_file") == "confirm"
