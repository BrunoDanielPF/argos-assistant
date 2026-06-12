from collections.abc import Callable
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from assistant.cli_commands import ArgosCompleter


PROMPT_STYLE = Style.from_dict(
    {
        "prompt": "bold #7ee787",
        "completion-menu.completion": "bg:#11182a #cbd5e1",
        "completion-menu.completion.current": "bg:#164e63 #ffffff",
        "completion-menu.meta.completion": "bg:#11182a #94a3b8",
        "completion-menu.meta.completion.current": "bg:#164e63 #cffafe",
    }
)


class ArgosPrompt:
    def __init__(
        self,
        *,
        interactive: bool,
        history_file: Path | None = None,
        fallback_reader: Callable[[str], str] | None = None,
        input=None,
        output=None,
    ) -> None:
        self.interactive = interactive
        self.history_file = history_file or Path.home() / ".argos" / "cli-history"
        self.fallback_reader = fallback_reader
        self.input = input
        self.output = output
        self.session = self._build_session() if interactive else None

    def _build_session(self) -> PromptSession:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        return PromptSession(
            history=FileHistory(str(self.history_file)),
            completer=ArgosCompleter(),
            auto_suggest=AutoSuggestFromHistory(),
            complete_while_typing=True,
            style=PROMPT_STYLE,
            input=self.input,
            output=self.output,
        )

    def read(self) -> str:
        if self.session is None:
            if self.fallback_reader is None:
                raise RuntimeError("Fallback reader is required outside an interactive TTY")
            return self.fallback_reader("argos")
        return self.session.prompt([("class:prompt", "argos ❯ ")])
