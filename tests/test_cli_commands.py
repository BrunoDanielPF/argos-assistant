from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from assistant.cli_commands import (
    COMMANDS,
    EXAMPLES,
    ArgosCompleter,
    command_for,
)


def test_command_catalog_describes_all_existing_interactive_commands():
    names = {command.name for command in COMMANDS}

    assert names == {
        "/context",
        "/cwd",
        "/help",
        "/history",
        "/memory",
        "/memo",
        "/open",
        "/pwd",
        "/remember",
    }
    assert command_for("/open").arguments == "<caminho|numero>"
    assert command_for("/open").description
    assert all(command.category for command in COMMANDS)


def test_natural_language_examples_are_kept_separate_from_commands():
    assert EXAMPLES
    assert all(not example.text.startswith("/") for example in EXAMPLES)
    assert {example.category for example in EXAMPLES} >= {
        "Arquivos",
        "Memoria",
        "Rotinas",
    }


def test_completer_filters_slash_commands_and_exposes_metadata():
    completions = list(
        ArgosCompleter().get_completions(
            Document("/op", cursor_position=3),
            CompleteEvent(completion_requested=True),
        )
    )

    assert [item.text for item in completions] == ["/open"]
    assert completions[0].display_meta_text == "Abrir arquivo ou resultado de busca"


def test_completer_shows_examples_for_empty_input():
    completions = list(
        ArgosCompleter().get_completions(
            Document("", cursor_position=0),
            CompleteEvent(completion_requested=True),
        )
    )

    assert any(item.text == "/help" for item in completions)
    assert any(item.text == "buscar documentos deste projeto" for item in completions)
