from collections import defaultdict

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from assistant.cli_commands import COMMANDS, EXAMPLES


class ArgosUI:
    def __init__(
        self,
        console: Console,
        *,
        markdown_enabled: bool = True,
    ) -> None:
        self.console = console
        self.markdown_enabled = markdown_enabled

    def render_session_header(self, *, session_id: str, mode: str, cwd: str) -> None:
        title = Text("ARGOS", style="bold cyan")
        metadata = Text()
        metadata.append(session_id, style="bold")
        metadata.append("  ·  ")
        metadata.append(mode)
        metadata.append("  ·  ")
        metadata.append(cwd, style="dim")
        self.console.print(Panel(metadata, title=title, border_style="bright_black"))

    def render_result(self, result: dict) -> None:
        ok = bool(result["ok"])
        title = "Resposta" if ok else "Erro"
        border_style = "cyan" if ok else "red"
        body = self._message_renderable(str(result["message"]))
        self.console.print(Panel(body, title=title, border_style=border_style))

        suggestions = result.get("suggestions", [])
        if suggestions:
            lines = [
                Text(f"{index}. {suggestion['text']}", style="dim")
                for index, suggestion in enumerate(suggestions, start=1)
            ]
            self.console.print(
                Panel(
                    Group(*lines),
                    title="Proximas acoes",
                    border_style="bright_black",
                )
            )

    def render_help(self) -> None:
        grouped = defaultdict(list)
        for command in COMMANDS:
            grouped[command.category].append(command)

        table = Table(title="Comandos", header_style="bold cyan", box=None)
        table.add_column("Categoria", style="dim")
        table.add_column("Comando", style="bold")
        table.add_column("Descricao")
        for category, commands in grouped.items():
            for command in commands:
                usage = " ".join(part for part in (command.name, command.arguments) if part)
                table.add_row(category, usage, command.description)
        self.console.print(table)

        example_lines = [
            Text.assemble(
                (f"{example.category}: ", "bold"),
                example.text,
            )
            for example in EXAMPLES
        ]
        self.console.print(
            Panel(
                Group(*example_lines),
                title="Exemplos de pedidos",
                border_style="bright_black",
            )
        )

    def _message_renderable(self, message: str):
        if not self.markdown_enabled:
            return Text(message)
        try:
            return Markdown(message, code_theme="monokai")
        except Exception:
            return Text(message)
