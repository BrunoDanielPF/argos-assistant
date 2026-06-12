import pytest

from assistant.intent.pending_resolver import (
    PendingClarificationResolver,
    PendingResolutionStatus,
)


def _path_pending(**overrides) -> dict:
    pending = {
        "field": "path",
        "question": "Qual arquivo devo usar?",
        "action": {
            "capability": "write_file",
            "arguments": {"content": "novo", "write_mode": "replace"},
        },
        "options": [],
        "accept_free_text": True,
    }
    pending.update(overrides)
    return pending


def test_pending_path_accepts_filename_with_extension():
    resolution = PendingClarificationResolver().resolve(
        "teste.txt",
        _path_pending(),
    )

    assert resolution.status == PendingResolutionStatus.RESOLVED
    assert resolution.value == "teste.txt"


@pytest.mark.parametrize(
    "path",
    [
        "C:\\workspace\\teste.txt",
        "/home/user/teste.txt",
        "./docs/teste.txt",
        "../docs/teste.txt",
        "docs/teste.txt",
    ],
)
def test_pending_path_accepts_absolute_and_relative_paths(path):
    resolution = PendingClarificationResolver().resolve(path, _path_pending())

    assert resolution.status == PendingResolutionStatus.RESOLVED
    assert resolution.value == path


def test_pending_path_accepts_valid_numeric_option():
    pending = _path_pending(
        options=[
            {"id": "C:\\workspace\\one.md", "label": "one.md"},
            {"id": "C:\\workspace\\two.md", "label": "two.md"},
        ]
    )

    resolution = PendingClarificationResolver().resolve("1", pending)

    assert resolution.status == PendingResolutionStatus.RESOLVED
    assert resolution.value == "C:\\workspace\\one.md"


def test_pending_path_accepts_existing_option_label():
    pending = _path_pending(
        options=[
            {"id": "C:\\workspace\\one.md", "label": "arquivo principal"},
        ]
    )

    resolution = PendingClarificationResolver().resolve(
        "arquivo principal",
        pending,
    )

    assert resolution.status == PendingResolutionStatus.RESOLVED
    assert resolution.value == "C:\\workspace\\one.md"


@pytest.mark.parametrize(
    "message",
    [
        "não quero usar LangChain no core do Argos",
        "voce consegue criar uma skill?",
    ],
)
def test_pending_path_rejects_conversational_statement(message):
    resolution = PendingClarificationResolver().resolve(
        message,
        _path_pending(),
    )

    assert resolution.status == PendingResolutionStatus.NEW_INTENT
    assert resolution.value is None


@pytest.mark.parametrize(
    "message",
    [
        "oque voce pode fazer?",
        "como voce pode me ajudar?",
    ],
)
def test_pending_path_rejects_capability_question(message):
    resolution = PendingClarificationResolver().resolve(
        message,
        _path_pending(),
    )

    assert resolution.status == PendingResolutionStatus.HELP
    assert resolution.value is None


def test_pending_path_treats_explicit_file_creation_as_new_intent():
    resolution = PendingClarificationResolver().resolve(
        "crie um arquivo chamado teste.txt",
        _path_pending(),
    )

    assert resolution.status == PendingResolutionStatus.NEW_INTENT
    assert resolution.value is None


def test_pending_path_recognizes_capability_question_by_meaning():
    resolution = PendingClarificationResolver().resolve(
        "qual as suas habilidades para me ajudar",
        _path_pending(),
    )

    assert resolution.status == PendingResolutionStatus.HELP
    assert resolution.value is None
