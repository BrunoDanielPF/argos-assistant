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
    result = runner.invoke(app, ["chat", "--direct", "open ollama website"])

    assert result.exit_code == 0
    assert "Opened https://ollama.com" in result.stdout
    assert "Ask me to open documentation next" in result.stdout


def test_cli_chat_uses_gateway_by_default(monkeypatch):
    calls = []

    class FakeGatewayClient:
        def chat(self, session_id, content, cwd=None):
            calls.append((session_id, content, cwd))
            return type(
                "Response",
                (),
                {
                    "ok": True,
                    "message": "Gateway handled",
                    "suggestions": [],
                },
            )()

    monkeypatch.setattr(
        "assistant.cli.build_gateway_client",
        lambda: FakeGatewayClient(),
    )

    result = CliRunner().invoke(
        app,
        ["chat", "--session", "projeto-x", "continue"],
    )

    assert result.exit_code == 0
    assert calls == [("projeto-x", "continue", None)]
    assert "Gateway handled" in result.stdout


def test_cli_gateway_unavailable_does_not_fallback_silently(monkeypatch):
    from assistant.gateway.client import GatewayUnavailable

    class FakeGatewayClient:
        def chat(self, session_id, content, cwd=None):
            raise GatewayUnavailable("offline")

    monkeypatch.setattr(
        "assistant.cli.build_gateway_client",
        lambda: FakeGatewayClient(),
    )

    result = CliRunner().invoke(app, ["chat", "oi"])

    assert result.exit_code == 1
    assert "argos start" in result.stdout


def test_tools_pending_lists_session_workflows(monkeypatch):
    class FakeGatewayClient:
        def list_capability_workflows(self, session_id=None):
            assert session_id == "project-1"
            return [
                {
                    "workflow_id": "workflow-123",
                    "status": "WAITING_TOOL_APPROVAL",
                    "tool_name": "local.file.metadata_stat",
                    "tool_version": "1.0.0",
                }
            ]

    monkeypatch.setattr(
        "assistant.cli.build_gateway_client",
        lambda: FakeGatewayClient(),
    )

    result = CliRunner().invoke(
        app,
        ["tools", "pending", "--session", "project-1"],
    )

    assert result.exit_code == 0
    assert "workflow-123" in result.stdout
    assert "WAITING_TOOL_APPROVAL" in result.stdout


def test_tools_cancel_cancels_workflow(monkeypatch):
    calls = []

    class FakeGatewayClient:
        def cancel_capability_workflow(self, workflow_id):
            calls.append(workflow_id)
            return type(
                "Response",
                (),
                {
                    "ok": True,
                    "message": "Workflow cancelado.",
                    "workflow_id": workflow_id,
                    "workflow_status": "TOOL_APPROVAL_CANCELLED",
                },
            )()

    monkeypatch.setattr(
        "assistant.cli.build_gateway_client",
        lambda: FakeGatewayClient(),
    )

    result = CliRunner().invoke(
        app,
        ["tools", "cancel", "workflow-123"],
    )

    assert result.exit_code == 0
    assert calls == ["workflow-123"]
    assert "Workflow cancelado" in result.stdout


def test_cli_prompts_and_resumes_gateway_confirmation(monkeypatch):
    from assistant.runtime.contracts import (
        AgentResponse,
        ConfirmationRequest,
    )

    decisions = []

    class FakeGatewayClient:
        def chat(self, session_id, content, cwd=None):
            return AgentResponse(
                session_id=session_id,
                run_id="run-1",
                ok=False,
                status="waiting_confirmation",
                message="Preciso de confirmacao.",
                confirmation=ConfirmationRequest(
                    confirmation_id="confirm-1",
                    capability="create_file",
                    arguments_summary={
                        "path": "C:\\Users\\frand\\receita.md",
                        "content_length": 120,
                    },
                    permissions=[
                        "write:C:\\Users\\frand\\receita.md"
                    ],
                    question="Autorizar a criacao do arquivo?",
                ),
            )

        def confirm(self, confirmation_id, approved):
            decisions.append((confirmation_id, approved))
            return AgentResponse(
                session_id="default",
                run_id="run-1",
                ok=True,
                message="Arquivo criado",
            )

    monkeypatch.setattr(
        "assistant.cli.build_gateway_client",
        lambda: FakeGatewayClient(),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "sim")

    result = CliRunner().invoke(app, ["chat", "crie a receita"])

    assert result.exit_code == 0
    assert "C:\\Users\\frand\\receita.md" in result.stdout
    assert "write:C:\\Users\\frand\\receita.md" in result.stdout
    assert "Arquivo criado" in result.stdout
    assert decisions == [("confirm-1", True)]


def test_cli_renders_guided_dry_run_before_confirmation(monkeypatch):
    from assistant.runtime.contracts import AgentResponse, ConfirmationRequest

    class FakeGatewayClient:
        def chat(self, session_id, content, cwd=None):
            return AgentResponse(
                session_id=session_id,
                run_id="run-1",
                ok=False,
                status="waiting_confirmation",
                message="Preciso de confirmacao.",
                confirmation=ConfirmationRequest(
                    confirmation_id="confirm-1",
                    capability="file.move_many",
                    arguments_summary={"pattern": "*.txt"},
                    permissions=["write:C:\\workspace\\backup"],
                    question="Autorizar?",
                    dry_run={
                        "action": "file.move_many",
                        "resources_affected": [
                            "C:\\workspace",
                            "C:\\workspace\\backup",
                        ],
                        "risk": "high",
                        "permissions_required": [
                            "write:C:\\workspace",
                            "write:C:\\workspace\\backup",
                        ],
                        "requires_confirmation": True,
                        "expected_result": (
                            "Os arquivos .txt seriam movidos para backup."
                        ),
                        "can_execute": True,
                    },
                ),
            )

        def confirm(self, confirmation_id, approved):
            return AgentResponse(
                session_id="default",
                run_id="run-1",
                ok=False,
                message="Cancelado",
            )

    monkeypatch.setattr("assistant.cli.build_gateway_client", lambda: FakeGatewayClient())
    monkeypatch.setattr("builtins.input", lambda prompt: "nao")

    result = CliRunner().invoke(app, ["chat", "mova os txt"])

    assert result.exit_code == 0
    assert "Impacto previsto" in result.stdout
    assert "Recursos afetados" in result.stdout
    assert "Executar com confirmacao" in result.stdout
    assert "Revisar detalhes" in result.stdout
    assert "Cancelar" in result.stdout


def test_interactive_explains_keyboard_interruption(monkeypatch):
    monkeypatch.setattr(
        "assistant.cli.typer.prompt",
        lambda prompt: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    result = CliRunner().invoke(app, ["interactive", "--direct"])

    assert result.exit_code == 0
    assert "Interacao interrompida" in result.stdout


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
    result = runner.invoke(app, ["chat", "--direct", "oi"])

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
    result = runner.invoke(app, ["chat", "--direct", "search notes"])

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
    result = runner.invoke(
        app,
        ["interactive", "--direct"],
        input="open ollama website\nexit\n",
    )

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
    result = runner.invoke(app, ["--direct"], input="oi\nexit\n")

    assert result.exit_code == 0
    assert "Digite /help para explorar comandos" in result.stdout
    assert "argos:" in result.stdout
    assert "Handled oi" in result.stdout
    assert prompts == ["oi"]


def test_cli_interactive_renders_structured_header_and_help(monkeypatch):
    class FakeMemory:
        def snapshot(self) -> dict:
            return {"context": {"current_cwd": "C:\\workspace"}}

    class FakeAgent:
        memory = FakeMemory()

        def handle(self, user_input: str) -> dict:
            raise AssertionError("agent should not handle /help")

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    result = CliRunner().invoke(
        app,
        ["interactive", "--direct"],
        input="/help\nexit\n",
    )

    assert result.exit_code == 0
    assert "ARGOS" in result.stdout
    assert "C:\\workspace" in result.stdout
    assert "Comandos" in result.stdout
    assert "/open" in result.stdout
    assert "Exemplos de pedidos" in result.stdout


def test_cli_chat_renders_markdown_response(monkeypatch):
    class FakeAgent:
        def handle(self, user_input: str) -> dict:
            return {
                "ok": True,
                "message": "## Arquivos\n\n- `README.md`",
                "suggestions": [],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    result = CliRunner().invoke(app, ["chat", "--direct", "liste arquivos"])

    assert result.exit_code == 0
    assert "Resposta" in result.stdout
    assert "Arquivos" in result.stdout
    assert "README.md" in result.stdout


def test_cli_accepts_no_color_root_option(monkeypatch):
    class FakeAgent:
        def handle(self, user_input: str) -> dict:
            return {"ok": True, "message": "Tudo certo", "suggestions": []}

    monkeypatch.setattr("assistant.cli.build_agent", lambda confirmer=None: FakeAgent())

    result = CliRunner().invoke(
        app,
        ["--no-color", "chat", "--direct", "oi"],
    )

    assert result.exit_code == 0
    assert "Tudo certo" in result.stdout
    assert "\x1b[" not in result.stdout


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
    result = runner.invoke(
        app,
        ["interactive", "--direct"],
        input="/cwd C:\\temp\nexit\n",
    )

    assert result.exit_code == 0
    assert fake_memory.context_updates == [
        {"current_cwd": "C:\\temp", "default_search_root": "C:\\temp"}
    ]


def test_build_agent_sets_user_home_context():
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
    result = runner.invoke(
        app,
        ["interactive", "--direct"],
        input="/pwd\n/context\nexit\n",
    )

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
    result = runner.invoke(
        app,
        ["interactive", "--direct"],
        input="/history\nexit\n",
    )

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
    result = runner.invoke(
        app,
        ["interactive", "--direct"],
        input="/open C:\\temp\\notes.txt\nexit\n",
    )

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
    result = runner.invoke(
        app,
        ["interactive", "--direct"],
        input="/open 1\nexit\n",
    )

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


def test_cli_tools_list_does_not_show_specific_development_template(monkeypatch):
    from assistant.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["tools", "list"])

    assert result.exit_code == 0
    assert "local.spring.create_project" not in result.stdout


def test_cli_tools_inspect_reports_removed_specific_development_template():
    runner = CliRunner()

    result = runner.invoke(app, ["tools", "inspect", "local.spring.create_project"])

    assert result.exit_code == 1
    assert "Tool nao encontrada" in result.stdout


def test_cli_tools_help_lists_lifecycle_commands():
    runner = CliRunner()

    result = runner.invoke(app, ["tools", "--help"])

    assert result.exit_code == 0
    for command in ("register", "approve", "install", "enable", "disable", "generate"):
        assert command in result.stdout


def test_cli_logs_handles_invalid_terminal_characters(monkeypatch, tmp_path):
    log_file = tmp_path / "gateway.log"
    log_file.write_bytes(b"erro: \xff\n")
    monkeypatch.setenv("ARGOS_GATEWAY_LOG_FILE", str(log_file))

    result = CliRunner().invoke(app, ["logs"])

    assert result.exit_code == 0
    assert "erro:" in result.stdout
