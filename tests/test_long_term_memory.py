from datetime import date

from assistant.memory.long_term import LongTermMemoryStore


def test_long_term_memory_appends_learning_to_markdown(tmp_path):
    store = LongTermMemoryStore(tmp_path)

    target = store.remember(
        learning="O usuario prefere documentacao em portugues.",
        context="documentacao",
        source="correcao do usuario",
        today=date(2026, 6, 5),
    )

    assert target == tmp_path / "correcoes.md"
    assert target.read_text(encoding="utf-8") == (
        "# Correcoes\n\n"
        "## O usuario prefere documentacao em portugues\n\n"
        "- Data: 2026-06-05\n"
        "- Contexto: documentacao\n"
        "- Aprendizado: O usuario prefere documentacao em portugues.\n"
        "- Fonte: correcao do usuario\n\n"
    )


def test_long_term_memory_rejects_sensitive_learning(tmp_path):
    store = LongTermMemoryStore(tmp_path)

    result = store.validate_learning("minha senha e 123456")

    assert result.ok is False
    assert "sensivel" in result.reason


def test_long_term_memory_searches_relevant_markdown_entries(tmp_path):
    store = LongTermMemoryStore(tmp_path)
    store.remember(
        learning="O usuario prefere respostas objetivas em portugues.",
        context="preferencias",
        today=date(2026, 6, 5),
    )
    store.remember(
        learning="O projeto usa Ollama com qwen3:4b.",
        context="modelo",
        today=date(2026, 6, 5),
    )

    results = store.search("como devo responder para o usuario?", max_results=1)

    assert len(results) == 1
    assert results[0]["learning"] == "O usuario prefere respostas objetivas em portugues."
    assert results[0]["source_file"] == "correcoes.md"
