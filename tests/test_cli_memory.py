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
