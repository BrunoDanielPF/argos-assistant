from pathlib import Path

from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

from assistant.cli_prompt import ArgosPrompt


def test_prompt_uses_fallback_reader_when_not_interactive():
    prompts = []
    prompt = ArgosPrompt(
        interactive=False,
        fallback_reader=lambda label: prompts.append(label) or "/help",
    )

    assert prompt.read() == "/help"
    assert prompts == ["argos"]


def test_prompt_builds_interactive_session_with_history(tmp_path):
    prompt = ArgosPrompt(
        interactive=True,
        history_file=tmp_path / "history",
        input=DummyInput(),
        output=DummyOutput(),
    )

    assert prompt.session is not None
    assert prompt.history_file == Path(tmp_path / "history")
    assert prompt.session.completer is not None
