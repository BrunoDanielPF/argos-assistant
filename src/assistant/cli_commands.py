from dataclasses import dataclass

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


@dataclass(frozen=True)
class CommandSpec:
    name: str
    description: str
    category: str
    arguments: str = ""


@dataclass(frozen=True)
class ExampleSpec:
    text: str
    category: str


COMMANDS = (
    CommandSpec("/help", "Mostrar comandos e exemplos", "Ajuda"),
    CommandSpec("/open", "Abrir arquivo ou resultado de busca", "Arquivos", "<caminho|numero>"),
    CommandSpec("/cwd", "Alterar diretorio da sessao", "Contexto", "<caminho>"),
    CommandSpec("/pwd", "Mostrar diretorio atual", "Contexto"),
    CommandSpec("/context", "Mostrar contexto da sessao", "Contexto"),
    CommandSpec("/history", "Mostrar historico da conversa", "Sessao"),
    CommandSpec("/memory", "Listar memorias persistentes", "Memoria"),
    CommandSpec("/memo", "Alias para /memory", "Memoria"),
    CommandSpec("/remember", "Salvar um aprendizado", "Memoria", "<aprendizado>"),
)

EXAMPLES = (
    ExampleSpec("buscar documentos deste projeto", "Arquivos"),
    ExampleSpec("abrir o segundo resultado", "Arquivos"),
    ExampleSpec("lembre que prefiro respostas curtas", "Memoria"),
    ExampleSpec("agende um lembrete para amanha", "Rotinas"),
)


def command_for(name: str) -> CommandSpec:
    normalized = name.strip().split(maxsplit=1)[0]
    for command in COMMANDS:
        if command.name == normalized:
            return command
    raise KeyError(name)


class ArgosCompleter(Completer):
    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            for command in COMMANDS:
                if command.name.startswith(text):
                    yield Completion(
                        command.name,
                        start_position=-len(text),
                        display_meta=command.description,
                    )
            return

        if text.strip():
            return

        for command in COMMANDS:
            yield Completion(
                command.name,
                display_meta=f"Comando · {command.description}",
            )
        for example in EXAMPLES:
            yield Completion(
                example.text,
                display_meta=f"Exemplo · {example.category}",
            )
