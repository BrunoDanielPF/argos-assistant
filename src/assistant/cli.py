import builtins
import json
import os
from pathlib import Path
import sys

import typer
from rich.console import Console

from assistant.agent import AssistantAgent
from assistant.capabilities.registry import build_default_registry
from assistant.config import AppConfig
from assistant.execution.executor import ActionExecutor
from assistant.execution.policy import decide_policy
from assistant.files.resolver import FileResolver
from assistant.llm.ollama_client import OllamaClient
from assistant.memory.long_term import LongTermMemoryStore
from assistant.memory.session import SessionMemory
from assistant.planner import Planner
from assistant.tools.catalog import ToolCatalog
from assistant.tools.audit import ToolAuditLog
from assistant.tools.generator import ToolDraftGenerator
from assistant.tools.installer import ToolInstaller
from assistant.tools.manifest import load_tool_manifest
from assistant.tools.permissions import UnsafeToolPermission, expand_permissions
from assistant.tools.runner import ToolRunner
from assistant.tools.state import ToolStateStore, hash_tool_files
from assistant.tools.validator import ToolValidator

ASSISTANT_NAME = "Argos"
ASSISTANT_PROMPT = ASSISTANT_NAME.lower()
CLI_DESCRIPTION = f"{ASSISTANT_NAME} Local AI Assistant"

app = typer.Typer(help=CLI_DESCRIPTION)
tools_app = typer.Typer(help="Gerenciar tools do Argos")
app.add_typer(tools_app, name="tools")
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
        if "." in capability_name:
            tool = build_tool_catalog().get_enabled(capability_name)
            if tool is not None:
                try:
                    permissions = expand_permissions(
                        tool.manifest.permissions,
                        arguments,
                    )
                    console.print(
                        "Effective permissions: "
                        f"write={permissions.filesystem_write}, "
                        f"read={permissions.filesystem_read}, "
                        f"network={permissions.network_enabled}, "
                        f"subprocess={permissions.subprocess_executables}"
                    )
                except UnsafeToolPermission as exc:
                    console.print(f"[ERROR] Unsafe tool permissions: {exc}")
                    return False
    if not sys.stdin or not sys.stdin.isatty():
        console.print("Non-interactive session detected; cancelling confirmation-required action.")
        return False

    try:
        answer = builtins.input("Execute this action? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes", "s", "sim"}


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
    tool_catalog = build_tool_catalog(config)
    capabilities = [
        item.name for item in build_default_registry(tool_catalog).list_all()
    ]
    memory = SessionMemory()
    memory.set_context(
        current_cwd=os.getcwd(),
        default_search_root=os.getcwd(),
        user_home=str(Path.home()),
    )
    planner = Planner(
        OllamaClient(
            model=config.model,
            base_url=config.ollama_base_url,
            timeout_seconds=config.ollama_timeout_seconds,
            keep_alive=config.ollama_keep_alive,
            think=config.ollama_think,
            options={
                "num_predict": config.ollama_num_predict,
                "num_ctx": config.ollama_num_ctx,
            },
        ),
        capabilities=capabilities,
        loading_context=lambda: console.status("Argos esta pensando..."),
        tool_definitions=[
            {
                "name": tool.manifest.name,
                "description": tool.manifest.description,
                "input_schema": tool.manifest.input_schema,
            }
            for tool in tool_catalog.list_enabled()
        ],
    )
    executor = ActionExecutor()
    if hasattr(executor, "configure_tools"):
        executor.configure_tools(
            tool_catalog,
            ToolRunner(audit_log=ToolAuditLog(config.tool_audit_file)),
        )
    long_term_memory = LongTermMemoryStore(config.memory_dir)
    return AssistantAgent(
        planner=planner,
        executor=executor,
        memory=memory,
        long_term_memory=long_term_memory,
        policy_decider=lambda capability: (
            "confirm"
            if tool_catalog.get_enabled(capability) is not None
            else decide_policy(capability)
        ),
        confirmer=confirmer,
        file_resolver=FileResolver(),
    )


def build_tool_catalog(config: AppConfig | None = None) -> ToolCatalog:
    config = config or AppConfig()
    bundled_root = Path(__file__).resolve().parents[2] / "tools"
    return ToolCatalog(
        tools_root=config.tools_dir,
        state_store=ToolStateStore(config.tool_state_file),
        bundled_root=bundled_root,
        envs_root=config.tool_envs_dir,
    )


@tools_app.command("list")
def tools_list() -> None:
    tools = build_tool_catalog().list_enabled()
    if not tools:
        console.print("Nenhuma tool habilitada.")
        return
    for tool in tools:
        source = "bundled" if tool.trusted else "local"
        console.print(
            f"{tool.manifest.name} {tool.manifest.version} "
            f"[{source}] - {tool.manifest.description}",
            markup=False,
        )


@tools_app.command("inspect")
def tools_inspect(name: str) -> None:
    tool = build_tool_catalog().get_enabled(name)
    if tool is None:
        console.print(f"[ERROR] Tool nao encontrada ou desabilitada: {name}")
        raise typer.Exit(code=1)
    payload = {
        "name": tool.manifest.name,
        "version": tool.manifest.version,
        "description": tool.manifest.description,
        "input_schema": tool.manifest.input_schema,
        "output_schema": tool.manifest.output_schema,
        "permissions": tool.manifest.permissions.model_dump(),
    }
    console.print(json.dumps(payload, indent=2, ensure_ascii=False), markup=False)


@tools_app.command("validate")
def tools_validate(path: str) -> None:
    report = ToolValidator().validate(Path(path))
    if report.ok:
        console.print("[OK] Tool valida")
        return
    for finding in report.findings:
        console.print(f"[ERROR] {finding.code}: {finding.message}")
    raise typer.Exit(code=1)


@tools_app.command("register")
def tools_register(path: str) -> None:
    config = AppConfig()
    tool_dir = Path(path)
    manifest = load_tool_manifest(tool_dir)
    report = ToolValidator().validate(tool_dir)
    if not report.ok:
        console.print("[ERROR] Tool invalida; execute tools validate para detalhes.")
        raise typer.Exit(code=1)
    store = ToolStateStore(config.tool_state_file)
    store.register_draft(manifest.name, manifest.version, hash_tool_files(tool_dir))
    store.transition(manifest.name, manifest.version, "validating")
    store.transition(manifest.name, manifest.version, "validated")
    console.print(f"[OK] Draft registrado: {manifest.name}@{manifest.version}")


@tools_app.command("approve")
def tools_approve(name: str, version: str) -> None:
    store = ToolStateStore(AppConfig().tool_state_file)
    store.transition(name, version, "approved")
    console.print(f"[OK] Tool aprovada: {name}@{version}")


@tools_app.command("install")
def tools_install(path: str) -> None:
    config = AppConfig()
    installed = ToolInstaller(
        tools_root=config.tools_dir,
        envs_root=config.tool_envs_dir,
        state_store=ToolStateStore(config.tool_state_file),
    ).install(Path(path))
    console.print(f"[OK] Tool instalada em {installed}")


@tools_app.command("enable")
def tools_enable(name: str, version: str) -> None:
    store = ToolStateStore(AppConfig().tool_state_file)
    store.transition(name, version, "enabled")
    console.print(f"[OK] Tool habilitada: {name}@{version}")


@tools_app.command("disable")
def tools_disable(name: str, version: str) -> None:
    store = ToolStateStore(AppConfig().tool_state_file)
    store.transition(name, version, "disabled")
    console.print(f"[OK] Tool desabilitada: {name}@{version}")


@tools_app.command("generate")
def tools_generate(definition: str) -> None:
    config = AppConfig()
    definition_payload = json.loads(Path(definition).read_text(encoding="utf-8"))
    draft = ToolDraftGenerator(
        drafts_root=config.tool_drafts_dir,
        state_store=ToolStateStore(config.tool_state_file),
    ).generate(definition_payload)
    console.print(
        f"[OK] Draft criado em {draft.path} com estado {draft.state}. "
        "Ele nao esta instalado nem habilitado."
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
