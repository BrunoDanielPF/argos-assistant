import builtins
import os
import sys

import typer
from rich.console import Console

from assistant.agent import AssistantAgent
from assistant.capabilities.registry import build_default_registry
from assistant.config import AppConfig
from assistant.execution.executor import ActionExecutor
from assistant.llm.ollama_client import OllamaClient
from assistant.memory.long_term import LongTermMemoryStore
from assistant.memory.session import SessionMemory
from assistant.planner import Planner

ASSISTANT_NAME = "Argos"
ASSISTANT_PROMPT = ASSISTANT_NAME.lower()
CLI_DESCRIPTION = f"{ASSISTANT_NAME} Local AI Assistant"

app = typer.Typer(help=CLI_DESCRIPTION)
console = Console()


def confirm_action(capability_name: str, arguments: dict) -> bool:
    if capability_name == "search_files":
        root = arguments.get("root", ".")
        pattern = arguments.get("pattern", "*")
        max_results = arguments.get("max_results", 5)
        console.print(
            "Confirmation required for search_files: "
            f"root={root}, pattern={pattern}, max_results={max_results}"
        )
    else:
        console.print(f"Confirmation required for {capability_name}: {arguments}")
    if not sys.stdin or not sys.stdin.isatty():
        console.print("Non-interactive session detected; cancelling confirmation-required action.")
        return False

    try:
        answer = builtins.input("Execute this action? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes"}


def render_result(result: dict) -> None:
    status = "OK" if result["ok"] else "ERROR"
    console.print(f"[{status}] {result['message']}")
    for suggestion in result["suggestions"]:
        console.print(f"- {suggestion['text']}")


def get_session_memory(agent):
    return getattr(agent, "memory", None) or getattr(agent, "_memory", None)


def resolve_open_target(agent, target: str) -> str:
    if target.isdigit():
        session_memory = get_session_memory(agent)
        snapshot = session_memory.snapshot() if session_memory is not None else {}
        search_results = snapshot.get("context", {}).get("last_search_results", [])
        index = int(target) - 1
        if 0 <= index < len(search_results):
            return search_results[index]
    return target


def extract_memory_learning(prompt: str) -> str | None:
    normalized = prompt.strip()
    lowered = normalized.lower()
    prefixes = ("lembre que ", "aprenda que ", "remember that ")
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return normalized[len(prefix):].strip()
    if lowered.startswith("corrigindo:"):
        return normalized.split(":", 1)[1].strip()
    return None


def confirm_memory(learning: str, target: str) -> bool:
    console.print("Memory save requested.")
    console.print(f"Learning: {learning}")
    console.print(f"Target: {target}")
    try:
        answer = builtins.input("Save this memory? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes", "s", "sim"}


def remember_learning(memory_store: LongTermMemoryStore, learning: str) -> None:
    validation = memory_store.validate_learning(learning)
    if not validation.ok:
        console.print(f"[ERROR] Memory not saved: {validation.reason}")
        return

    target = memory_store.memory_dir / "correcoes.md"
    if not confirm_memory(learning, str(target)):
        console.print("[ERROR] Memory save cancelled by user")
        return

    saved_path = memory_store.remember(learning)
    console.print(f"[OK] Memory saved to {saved_path}")


def render_persistent_memories(memory_store: LongTermMemoryStore) -> None:
    memories = memory_store.list_memories()
    if not memories:
        console.print("No persistent memories found.")
        return

    for index, memory in enumerate(memories, start=1):
        source_file = memory.get("source_file", "memory.md")
        context = memory.get("context", "geral")
        learning = memory.get("learning", "")
        console.print(f"{index}. [{context}] {learning} ({source_file})")


def build_agent(confirmer=None) -> AssistantAgent:
    config = AppConfig()
    capabilities = [item.name for item in build_default_registry().list_all()]
    memory = SessionMemory()
    memory.set_context(
        current_cwd=os.getcwd(),
        default_search_root=os.getcwd(),
    )
    planner = Planner(
        OllamaClient(
            model=config.model,
            base_url=config.ollama_base_url,
            timeout_seconds=config.ollama_timeout_seconds,
        ),
        capabilities=capabilities,
    )
    executor = ActionExecutor()
    long_term_memory = LongTermMemoryStore(config.memory_dir)
    return AssistantAgent(
        planner=planner,
        executor=executor,
        memory=memory,
        long_term_memory=long_term_memory,
        confirmer=confirmer,
    )


def run_interactive_session(
    agent: AssistantAgent,
    memory_store: LongTermMemoryStore | None = None,
) -> None:
    memory_store = memory_store or LongTermMemoryStore(AppConfig().memory_dir)
    console.print("Interactive mode. Type 'exit' to quit.")

    while True:
        prompt = typer.prompt(ASSISTANT_PROMPT)
        if prompt.strip().lower() in {"exit", "quit"}:
            console.print("Bye.")
            break
        if prompt.startswith("/cwd "):
            new_cwd = prompt[5:].strip()
            session_memory = get_session_memory(agent)
            if session_memory is not None:
                session_memory.set_context(
                    current_cwd=new_cwd,
                    default_search_root=new_cwd,
                )
            console.print(f"Updated session cwd to {new_cwd}")
            continue
        if prompt.startswith("/remember "):
            learning = prompt[10:].strip()
            remember_learning(memory_store, learning)
            continue
        if prompt.startswith("/open "):
            target_path = prompt[6:].strip()
            resolved_target = resolve_open_target(agent, target_path)
            result = agent.handle(f"open file {resolved_target}")
            render_result(result)
            continue
        if prompt.strip() == "/pwd":
            session_memory = get_session_memory(agent)
            snapshot = session_memory.snapshot() if session_memory is not None else {}
            context = snapshot.get("context", {})
            console.print(context.get("current_cwd", ""))
            continue
        if prompt.strip() == "/context":
            session_memory = get_session_memory(agent)
            snapshot = session_memory.snapshot() if session_memory is not None else {}
            console.print(snapshot.get("context", {}))
            continue
        if prompt.strip() == "/history":
            session_memory = get_session_memory(agent)
            snapshot = session_memory.snapshot() if session_memory is not None else {}
            for item in snapshot.get("history", []):
                console.print(f"{item['role']}: {item['content']}")
            continue
        if prompt.strip() == "/memory":
            render_persistent_memories(memory_store)
            continue
        learning = extract_memory_learning(prompt)
        if learning:
            remember_learning(memory_store, learning)
            continue
        if not prompt.strip():
            continue
        result = agent.handle(prompt)
        render_result(result)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """CLI entry point."""
    if ctx.invoked_subcommand is None:
        agent = build_agent(confirmer=confirm_action)
        run_interactive_session(agent)


@app.command()
def chat(prompt: str) -> None:
    agent = build_agent(confirmer=confirm_action)
    result = agent.handle(prompt)
    render_result(result)


@app.command()
def interactive() -> None:
    agent = build_agent(confirmer=confirm_action)
    run_interactive_session(agent)
