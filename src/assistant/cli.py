import builtins
import json
import os
from pathlib import Path
import sys

import typer
from rich.console import Console

from assistant.agent import AssistantAgent
from assistant.config import AppConfig
from assistant.gateway.client import GatewayClient, GatewayError, GatewayUnavailable
from assistant.gateway.process import GatewayProcessManager
from assistant.jobs.models import InvalidJobTransition, JobStatus
from assistant.jobs.repository import JobRepository
from assistant.memory.long_term import LongTermMemoryStore
from assistant.runtime.factory import RuntimeFactory
from assistant.tools.catalog import ToolCatalog
from assistant.tools.generator import ToolDraftGenerator
from assistant.tools.installer import ToolInstaller
from assistant.tools.manifest import load_tool_manifest
from assistant.tools.permissions import UnsafeToolPermission, expand_permissions
from assistant.tools.state import ToolStateStore, hash_tool_files
from assistant.tools.validator import ToolValidator

ASSISTANT_NAME = "Argos"
ASSISTANT_PROMPT = ASSISTANT_NAME.lower()
CLI_DESCRIPTION = f"{ASSISTANT_NAME} Local AI Assistant"

app = typer.Typer(help=CLI_DESCRIPTION)
tools_app = typer.Typer(help="Gerenciar tools do Argos")
jobs_app = typer.Typer(help="Consultar jobs do Argos")
app.add_typer(tools_app, name="tools")
app.add_typer(jobs_app, name="jobs")
console = Console()


def _safe_console_text(value: str) -> str:
    encoding = getattr(console.file, "encoding", None) or sys.stdout.encoding or "utf-8"
    return value.encode(encoding, errors="replace").decode(encoding, errors="replace")


class GatewayMemoryProxy:
    def __init__(
        self,
        client: GatewayClient,
        session_id: str,
        cwd: str,
    ) -> None:
        self._client = client
        self._session_id = session_id
        self._context = {
            "current_cwd": cwd,
            "default_search_root": cwd,
            "user_home": str(Path.home()),
        }

    def set_context(self, **kwargs) -> None:
        self._context.update(
            {key: value for key, value in kwargs.items() if value is not None}
        )

    def snapshot(self) -> dict:
        try:
            snapshot = self._client.get_session(self._session_id)
        except GatewayError:
            snapshot = {
                "history": [],
                "audit": [],
                "suggestions": [],
                "context": {},
            }
        snapshot["context"] = {
            **snapshot.get("context", {}),
            **self._context,
        }
        return snapshot


class GatewayAgentAdapter:
    def __init__(self, client: GatewayClient, session_id: str) -> None:
        self._client = client
        self._session_id = session_id
        self.memory = GatewayMemoryProxy(client, session_id, os.getcwd())

    def handle(self, user_input: str) -> dict:
        cwd = self.memory.snapshot()["context"].get("current_cwd")
        response = self._client.chat(
            self._session_id,
            user_input,
            cwd=cwd,
        )
        response = resolve_gateway_confirmation(self._client, response)
        return {
            "ok": response.ok,
            "message": response.message,
            "suggestions": response.suggestions,
        }


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
    return RuntimeFactory(
        config=AppConfig.load(),
        loading_context=lambda: console.status("Argos esta pensando..."),
    ).build_agent(confirmer=confirmer)


def build_gateway_client() -> GatewayClient:
    return GatewayClient(AppConfig.load())


def build_job_repository() -> JobRepository:
    return JobRepository(AppConfig.load().database_file)


def build_gateway_agent(session_id: str) -> GatewayAgentAdapter:
    return GatewayAgentAdapter(build_gateway_client(), session_id)


def render_gateway_error(exc: GatewayError) -> None:
    console.print(f"[ERROR] {exc}")
    if isinstance(exc, GatewayUnavailable):
        console.print("Execute 'argos start' para iniciar o servico residente.")


def resolve_gateway_confirmation(client: GatewayClient, response):
    if (
        getattr(response, "status", "completed") != "waiting_confirmation"
        or getattr(response, "confirmation", None) is None
    ):
        return response

    confirmation = response.confirmation
    console.print("Confirmacao necessaria:")
    console.print(f"Acao: {confirmation.capability}")
    for key, value in confirmation.arguments_summary.items():
        console.print(f"{key}: {value}")
    if confirmation.permissions:
        console.print("Permissoes:")
        for permission in confirmation.permissions:
            console.print(f"- {permission}")
    console.print(confirmation.question)
    try:
        answer = builtins.input("Executar esta acao? [s/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print(
            "[PENDING] A confirmacao continua pendente no gateway."
        )
        return response
    return client.confirm(
        confirmation.confirmation_id,
        approved=answer in {"y", "yes", "s", "sim"},
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


@jobs_app.command("list")
def jobs_list(limit: int = 20) -> None:
    repository = build_job_repository()
    try:
        jobs = repository.list_recent(limit=limit)
    finally:
        repository.close()
    if not jobs:
        console.print("Nenhum job encontrado.")
        return
    for job in jobs:
        console.print(
            f"{job.job_id[:8]}  {job.status.value}  "
            f"session={job.session_id} attempts={job.attempts} "
            f"updated={job.updated_at.isoformat()}"
        )


@jobs_app.command("show")
def jobs_show(job_id: str) -> None:
    repository = build_job_repository()
    try:
        job = repository.load(job_id)
    finally:
        repository.close()
    if job is None:
        console.print(f"Job nao encontrado: {job_id}")
        raise typer.Exit(code=1)
    console.print(f"job_id: {job.job_id}")
    console.print(f"session_id: {job.session_id}")
    console.print(f"run_id: {job.run_id}")
    console.print(f"status: {job.status.value}")
    console.print(f"attempts: {job.attempts}")
    console.print(f"created_at: {job.created_at.isoformat()}")
    console.print(f"updated_at: {job.updated_at.isoformat()}")
    if job.last_error:
        console.print(f"last_error: {job.last_error}")
    console.print("payload:")
    console.print(json.dumps(job.payload, ensure_ascii=False, indent=2))


@jobs_app.command("retry")
def jobs_retry(job_id: str) -> None:
    repository = build_job_repository()
    try:
        try:
            job = repository.transition(job_id, JobStatus.QUEUED)
        except KeyError:
            console.print(f"Job nao encontrado: {job_id}")
            raise typer.Exit(code=1)
        except InvalidJobTransition as exc:
            console.print(f"Nao foi possivel reenfileirar job: {exc}")
            raise typer.Exit(code=1)
    finally:
        repository.close()
    console.print(f"[OK] Job {job.job_id} status={job.status.value}")


@jobs_app.command("cancel")
def jobs_cancel(job_id: str) -> None:
    repository = build_job_repository()
    try:
        try:
            job = repository.transition(job_id, JobStatus.CANCELLED)
        except KeyError:
            console.print(f"Job nao encontrado: {job_id}")
            raise typer.Exit(code=1)
        except InvalidJobTransition as exc:
            console.print(f"Nao foi possivel cancelar job: {exc}")
            raise typer.Exit(code=1)
    finally:
        repository.close()
    console.print(f"[OK] Job {job.job_id} status={job.status.value}")


def run_interactive_session(
    agent: AssistantAgent,
    memory_store: LongTermMemoryStore | None = None,
) -> None:
    memory_store = memory_store or LongTermMemoryStore(AppConfig().memory_dir)
    console.print("Interactive mode. Type 'exit' to quit.")

    while True:
        try:
            prompt = typer.prompt(ASSISTANT_PROMPT)
        except (KeyboardInterrupt, EOFError, typer.Abort):
            console.print(
                "\nInteracao interrompida pelo terminal. "
                "Nenhuma nova solicitacao foi enviada."
            )
            break
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
def main(
    ctx: typer.Context,
    direct: bool = typer.Option(False, "--direct"),
    session: str = typer.Option("default", "--session"),
) -> None:
    """CLI entry point."""
    if ctx.invoked_subcommand is None:
        if direct:
            agent = build_agent(confirmer=confirm_action)
        else:
            agent = build_gateway_agent(session)
        try:
            run_interactive_session(agent)
        except GatewayError as exc:
            render_gateway_error(exc)
            raise typer.Exit(code=1) from exc


@app.command()
def chat(
    prompt: str,
    session: str = typer.Option("default", "--session"),
    direct: bool = typer.Option(False, "--direct"),
) -> None:
    try:
        if direct:
            agent = build_agent(confirmer=confirm_action)
            result = agent.handle(prompt)
        else:
            client = build_gateway_client()
            response = client.chat(session, prompt)
            response = resolve_gateway_confirmation(client, response)
            result = {
                "ok": response.ok,
                "message": response.message,
                "suggestions": response.suggestions,
            }
        render_result(result)
    except GatewayError as exc:
        render_gateway_error(exc)
        raise typer.Exit(code=1) from exc


@app.command()
def interactive(
    session: str = typer.Option("default", "--session"),
    direct: bool = typer.Option(False, "--direct"),
) -> None:
    if direct:
        agent = build_agent(confirmer=confirm_action)
    else:
        agent = build_gateway_agent(session)
    try:
        run_interactive_session(agent)
    except GatewayError as exc:
        render_gateway_error(exc)
        raise typer.Exit(code=1) from exc


@app.command()
def start() -> None:
    status = GatewayProcessManager(AppConfig.load()).start()
    console.print(f"[OK] Argos gateway iniciado (PID {status.pid}).")


@app.command()
def stop() -> None:
    status = GatewayProcessManager(AppConfig.load()).stop()
    if status.running:
        console.print(f"[ERROR] Argos gateway ainda ativo (PID {status.pid}).")
        raise typer.Exit(code=1)
    console.print("[OK] Argos gateway encerrado.")


@app.command()
def status() -> None:
    manager_status = GatewayProcessManager(AppConfig.load()).status()
    if not manager_status.running:
        console.print("Argos gateway parado.")
        raise typer.Exit(code=1)
    try:
        payload = build_gateway_client().status()
    except GatewayError as exc:
        render_gateway_error(exc)
        raise typer.Exit(code=1) from exc
    console.print(
        f"Argos gateway ativo (PID {manager_status.pid}), "
        f"modelo={payload['model']}, uptime={payload['uptime_seconds']:.1f}s."
    )


@app.command()
def logs() -> None:
    path = AppConfig.load().gateway_log_file
    if not path.exists():
        console.print("Nenhum log do gateway encontrado.")
        return
    console.print(_safe_console_text(path.read_text(encoding="utf-8", errors="replace")))
