from typer.testing import CliRunner
from assistant.cli import app, confirm_action


def test_cli_starts_and_exits_cleanly():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Argos" in result.stdout


def test_cli_chat_command_uses_agent(monkeypatch):
    class FakeAgent:
        def handle(self, user_input: str) -> dict:
            return {
                "ok": True,
                "message": "Opened https://ollama.com",
                "suggestions": [{"text": "Ask me to open documentation next"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["chat", "open ollama website"])

    assert result.exit_code == 0
    assert "Opened https://ollama.com" in result.stdout
    assert "Ask me to open documentation next" in result.stdout


def test_cli_chat_command_does_not_wrap_entire_agent_call_in_status(monkeypatch):
    class FakeAgent:
        def handle(self, user_input: str) -> dict:
            return {
                "ok": True,
                "message": "Handled",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    def fail_status(message):
        raise AssertionError("CLI must not keep spinner active around confirmations")

    monkeypatch.setattr("assistant.cli.console.status", fail_status)
    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["chat", "oi"])

    assert result.exit_code == 0
    assert "Handled" in result.stdout


def test_cli_chat_command_shows_failure_status(monkeypatch):
    class FakeAgent:
        def handle(self, user_input: str) -> dict:
            return {
                "ok": False,
                "message": "Action cancelled by user",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["chat", "search notes"])

    assert result.exit_code == 0
    assert "Action cancelled by user" in result.stdout
    assert "Ask me for the next step" in result.stdout


def test_cli_interactive_runs_until_exit(monkeypatch):
    prompts = []

    class FakeAgent:
        def handle(self, user_input: str) -> dict:
            prompts.append(user_input)
            return {
                "ok": True,
                "message": f"Handled {user_input}",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["interactive"], input="open ollama website\nexit\n")

    assert result.exit_code == 0
    assert "Handled open ollama website" in result.stdout
    assert prompts == ["open ollama website"]


def test_cli_without_subcommand_enters_interactive_mode(monkeypatch):
    prompts = []

    class FakeAgent:
        def handle(self, user_input: str) -> dict:
            prompts.append(user_input)
            return {
                "ok": True,
                "message": f"Handled {user_input}",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, input="oi\nexit\n")

    assert result.exit_code == 0
    assert "Interactive mode. Type 'exit' to quit." in result.stdout
    assert "argos:" in result.stdout
    assert "Handled oi" in result.stdout
    assert prompts == ["oi"]


def test_cli_interactive_updates_cwd(monkeypatch):
    class FakeMemory:
        def __init__(self) -> None:
            self.context_updates = []

        def set_context(self, **kwargs) -> None:
            self.context_updates.append(kwargs)

    fake_memory = FakeMemory()

    class FakeAgent:
        def __init__(self) -> None:
            self.memory = fake_memory

        def handle(self, user_input: str) -> dict:
            return {
                "ok": True,
                "message": f"Handled {user_input}",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["interactive"], input="/cwd C:\\temp\nexit\n")

    assert result.exit_code == 0
    assert fake_memory.context_updates == [
        {"current_cwd": "C:\\temp", "default_search_root": "C:\\temp"}
    ]


def test_build_agent_sets_user_home_context(monkeypatch):
    class FakePlanner:
        def __init__(self, *args, **kwargs) -> None:
            return None

    class FakeOllamaClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

    monkeypatch.setattr("assistant.cli.Planner", FakePlanner)
    monkeypatch.setattr("assistant.cli.OllamaClient", FakeOllamaClient)
    monkeypatch.setattr("assistant.cli.ActionExecutor", lambda: object())

    from assistant.cli import build_agent

    agent = build_agent()
    context = agent.memory.snapshot()["context"]

    assert "user_home" in context
    assert context["user_home"]


def test_cli_interactive_shows_pwd_and_context(monkeypatch):
    class FakeMemory:
        def snapshot(self) -> dict:
            return {
                "history": [],
                "audit": [],
                "suggestions": [],
                "context": {
                    "current_cwd": "C:\\workspace",
                    "default_search_root": "C:\\workspace",
                },
            }

    class FakeAgent:
        def __init__(self) -> None:
            self.memory = FakeMemory()

        def handle(self, user_input: str) -> dict:
            return {
                "ok": True,
                "message": f"Handled {user_input}",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["interactive"], input="/pwd\n/context\nexit\n")

    assert result.exit_code == 0
    assert "C:\\workspace" in result.stdout
    assert "default_search_root" in result.stdout


def test_cli_interactive_shows_history(monkeypatch):
    class FakeMemory:
        def snapshot(self) -> dict:
            return {
                "history": [
                    {"role": "user", "content": "open calculator"},
                    {"role": "assistant", "content": "Opened application calculator"},
                ],
                "audit": [],
                "suggestions": [],
                "context": {
                    "current_cwd": "C:\\workspace",
                    "default_search_root": "C:\\workspace",
                },
            }

    class FakeAgent:
        def __init__(self) -> None:
            self.memory = FakeMemory()

        def handle(self, user_input: str) -> dict:
            return {
                "ok": True,
                "message": f"Handled {user_input}",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["interactive"], input="/history\nexit\n")

    assert result.exit_code == 0
    assert "open calculator" in result.stdout
    assert "Opened application calculator" in result.stdout


def test_cli_interactive_opens_explicit_file(monkeypatch):
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
    result = runner.invoke(app, ["interactive"], input="/open C:\\temp\\notes.txt\nexit\n")

    assert result.exit_code == 0
    assert handled == ["open file C:\\temp\\notes.txt"]


def test_cli_interactive_opens_search_result_by_index(monkeypatch):
    handled = []

    class FakeMemory:
        def snapshot(self) -> dict:
            return {
                "history": [],
                "audit": [],
                "suggestions": [],
                "context": {
                    "current_cwd": "C:\\workspace",
                    "default_search_root": "C:\\workspace",
                    "last_search_results": ["C:\\workspace\\README.md", "C:\\workspace\\notes.txt"],
                },
            }

    class FakeAgent:
        def __init__(self) -> None:
            self.memory = FakeMemory()

        def handle(self, user_input: str) -> dict:
            handled.append(user_input)
            return {
                "ok": True,
                "message": f"Handled {user_input}",
                "suggestions": [{"text": "Ask me for the next step"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["interactive"], input="/open 1\nexit\n")

    assert result.exit_code == 0
    assert handled == ["open file C:\\workspace\\README.md"]


def test_confirm_action_formats_search_files_summary(monkeypatch):
    recorded = {}

    class FakeTtyStdin:
        def isatty(self) -> bool:
            return True

    def fake_input(message: str) -> str:
        recorded["message"] = message
        return "y"

    monkeypatch.setattr("assistant.cli.sys.stdin", FakeTtyStdin())
    monkeypatch.setattr("assistant.cli.builtins.input", fake_input)

    result = confirm_action(
        "search_files",
        {"root": "C:\\docs", "pattern": "notes.txt", "max_results": 3},
    )

    assert result is True
    assert recorded["message"] == "Execute this action? [y/N]: "


def test_confirm_action_accepts_portuguese_yes(monkeypatch):
    class FakeTtyStdin:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("assistant.cli.sys.stdin", FakeTtyStdin())
    monkeypatch.setattr("assistant.cli.builtins.input", lambda message: "sim")

    assert confirm_action("create_file", {"path": "C:\\temp\\hello.md"}) is True


def test_confirm_action_returns_false_on_abort(monkeypatch):
    class FakeTtyStdin:
        def isatty(self) -> bool:
            return True

    def fake_input(message: str) -> str:
        raise EOFError()

    monkeypatch.setattr("assistant.cli.sys.stdin", FakeTtyStdin())
    monkeypatch.setattr("assistant.cli.builtins.input", fake_input)

    result = confirm_action("search_files", {"root": "C:\\docs", "pattern": "notes.txt"})

    assert result is False


def test_confirm_action_returns_false_without_tty(monkeypatch):
    class FakeStdin:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("assistant.cli.sys.stdin", FakeStdin())

    result = confirm_action("search_files", {"root": "C:\\docs", "pattern": "notes.txt"})

    assert result is False
