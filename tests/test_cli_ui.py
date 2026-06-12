from io import StringIO

from rich.console import Console

from assistant.cli_ui import ArgosUI


def build_ui(*, color: bool = False, markdown: bool = True):
    output = StringIO()
    console = Console(
        file=output,
        force_terminal=color,
        color_system="standard" if color else None,
        width=100,
    )
    return ArgosUI(console, markdown_enabled=markdown), output


def test_render_result_formats_markdown_and_suggestions():
    ui, output = build_ui()

    ui.render_result(
        {
            "ok": True,
            "message": "## Resultado\n\n- `README.md`\n- **ARCHITECTURE.md**",
            "suggestions": [{"text": "Use /open 1"}],
        }
    )

    rendered = output.getvalue()
    assert "Resultado" in rendered
    assert "README.md" in rendered
    assert "Proximas acoes" in rendered
    assert "Use /open 1" in rendered


def test_render_result_falls_back_to_plain_text():
    ui, output = build_ui(markdown=False)

    ui.render_result(
        {
            "ok": False,
            "message": "[nao interpretar como Rich markup]",
            "suggestions": [],
        }
    )

    rendered = output.getvalue()
    assert "[nao interpretar como Rich markup]" in rendered
    assert "Erro" in rendered


def test_render_help_groups_commands_and_examples():
    ui, output = build_ui()

    ui.render_help()

    rendered = output.getvalue()
    assert "Comandos" in rendered
    assert "/open" in rendered
    assert "<caminho|numero>" in rendered
    assert "Exemplos de pedidos" in rendered
    assert "buscar documentos deste projeto" in rendered


def test_render_session_header_shows_mode_session_and_cwd():
    ui, output = build_ui()

    ui.render_session_header(
        session_id="projeto-x",
        mode="gateway",
        cwd="C:\\workspace",
    )

    rendered = output.getvalue()
    assert "ARGOS" in rendered
    assert "projeto-x" in rendered
    assert "gateway" in rendered
    assert "C:\\workspace" in rendered
