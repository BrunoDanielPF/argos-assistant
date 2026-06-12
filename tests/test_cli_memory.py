from pathlib import Path

from typer.testing import CliRunner

from assistant.cli import app


def test_cli_remember_command_confirms_and_persists_learning(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGOS_MEMORY_DIR", str(tmp_path))

    class FakeAgent:
        def __init__(self) -> None:
            self.memory = None

        def handle(self, user_input: str) -> dict:
            return {
                "ok": True,
                "message": f"Handled {user_input}",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["interactive"], input="/remember prefiro respostas curtas\ny\nexit\n")

    assert result.exit_code == 0
    assert "Memory saved" in result.stdout
    memory_file = Path(tmp_path) / "correcoes.md"
    assert "prefiro respostas curtas" in memory_file.read_text(encoding="utf-8")


def test_cli_lembre_que_uses_memory_flow_without_calling_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGOS_MEMORY_DIR", str(tmp_path))
    handled = []

    class FakeAgent:
        def __init__(self) -> None:
            self.memory = None

        def handle(self, user_input: str) -> dict:
            handled.append(user_input)
            return {
                "ok": True,
                "message": f"Handled {user_input}",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["interactive"], input="lembre que uso Windows\ny\nexit\n")

    assert result.exit_code == 0
    assert handled == []
    assert "uso Windows" in (Path(tmp_path) / "correcoes.md").read_text(encoding="utf-8")


def test_cli_time_based_lembre_que_goes_to_agent_instead_of_memory(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGOS_MEMORY_DIR", str(tmp_path))
    handled = []

    class FakeAgent:
        def __init__(self) -> None:
            self.memory = None

        def handle(self, user_input: str) -> dict:
            handled.append(user_input)
            return {
                "ok": True,
                "message": "Ainda nao consigo agendar lembretes por horario.",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    result = CliRunner().invoke(
        app,
        ["interactive", "--direct"],
        input="lembre que daqui 10 minutos criar documento\nexit\n",
    )

    assert result.exit_code == 0
    assert handled == ["lembre que daqui 10 minutos criar documento"]
    assert not (Path(tmp_path) / "correcoes.md").exists()


def test_cli_memory_command_lists_persistent_memories(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGOS_MEMORY_DIR", str(tmp_path))
    (tmp_path / "correcoes.md").write_text(
        "# Correcoes\n\n"
        "## Preferencia de resposta\n\n"
        "- Data: 2026-06-05\n"
        "- Contexto: preferencias\n"
        "- Aprendizado: O usuario prefere respostas objetivas em portugues.\n"
        "- Fonte: correcao do usuario\n\n",
        encoding="utf-8",
    )

    class FakeAgent:
        def __init__(self) -> None:
            self.memory = None

        def handle(self, user_input: str) -> dict:
            raise AssertionError("agent should not handle /memory")

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["interactive"], input="/memory\nexit\n")

    assert result.exit_code == 0
    assert "O usuario prefere respostas objetivas em portugues." in result.stdout
    assert "correcoes.md" in result.stdout


def test_cli_memory_command_handles_empty_memory(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGOS_MEMORY_DIR", str(tmp_path))

    class FakeAgent:
        def __init__(self) -> None:
            self.memory = None

        def handle(self, user_input: str) -> dict:
            raise AssertionError("agent should not handle /memory")

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["interactive"], input="/memory\nexit\n")

    assert result.exit_code == 0
    assert "No persistent memories found" in result.stdout


def test_cli_memo_is_memory_alias_and_never_reaches_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGOS_MEMORY_DIR", str(tmp_path))
    handled = []

    class FakeAgent:
        memory = None

        def handle(self, user_input: str) -> dict:
            handled.append(user_input)
            return {"ok": True, "message": user_input, "suggestions": []}

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    result = CliRunner().invoke(app, ["interactive"], input="/memo\nexit\n")

    assert result.exit_code == 0
    assert handled == []
    assert "No persistent memories found" in result.stdout


def test_unknown_slash_command_is_not_sent_to_agent(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGOS_MEMORY_DIR", str(tmp_path))
    handled = []

    class FakeAgent:
        memory = None

        def handle(self, user_input: str) -> dict:
            handled.append(user_input)
            return {"ok": True, "message": user_input, "suggestions": []}

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    result = CliRunner().invoke(app, ["interactive"], input="/memori\nexit\n")

    assert result.exit_code == 0
    assert handled == []
    assert "/memory" in result.stdout
