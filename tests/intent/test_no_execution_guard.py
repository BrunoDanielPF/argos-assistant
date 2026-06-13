import pytest

from assistant.intent.no_execution_guard import NoExecutionGuard


@pytest.mark.parametrize(
    "text",
    [
        "sem executar nada, qual seria o plano?",
        "nao execute, apenas explique",
        "não execute essa ação",
        "apenas explique como faria",
        "só me diga o plano",
    ],
)
def test_guard_recognizes_no_execution_directives(text):
    assert NoExecutionGuard().blocks(text) is True


def test_guard_does_not_block_normal_action_request():
    assert NoExecutionGuard().blocks("mova os arquivos txt") is False
