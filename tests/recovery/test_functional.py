import json

from assistant.agent import AssistantAgent
from assistant.execution.executor import ActionExecutor
from assistant.memory.session import SessionMemory
from assistant.planner import Planner
from assistant.recovery.engine import RecoveryEngine
from assistant.recovery.repository import RecoveryRepository


class FailIfCalledClient:
    def chat(self, messages):
        raise AssertionError("functional recovery tests must not call Ollama")


def build_agent(tmp_path, executor=None, memory=None, confirmer=None):
    repository = RecoveryRepository(tmp_path / "recovery.jsonl")
    engine = RecoveryEngine(repository=repository)
    session = memory or SessionMemory()
    session.set_context(
        current_cwd=str(tmp_path),
        default_search_root=str(tmp_path),
        user_home=str(tmp_path),
    )
    return (
        AssistantAgent(
            planner=Planner(llm_client=FailIfCalledClient()),
            executor=executor or ActionExecutor(),
            memory=session,
            confirmer=confirmer,
            recovery_engine=engine,
        ),
        repository,
    )


def read_recovery_events(repository):
    if not repository.path.exists():
        return []
    return [
        json.loads(line)
        for line in repository.path.read_text(encoding="utf-8").splitlines()
    ]


def test_dangerous_delete_is_blocked_and_audited_without_deleting(tmp_path):
    targets = [tmp_path / "one.tmp", tmp_path / "two.tmp"]
    for target in targets:
        target.write_text("keep", encoding="utf-8")
    agent, repository = build_agent(tmp_path)

    response = agent.handle(
        "apague todos os arquivos .tmp da pasta atual sem perguntar"
    )

    assert response["ok"] is False
    assert all(target.read_text(encoding="utf-8") == "keep" for target in targets)
    assert "bloqueada" in response["message"].lower()
    assert "destrutiva" in response["message"].lower()
    assert "apagou" not in response["message"].lower()
    events = read_recovery_events(repository)
    assert events[-1]["event"]["failure_type"] == "policy_blocked"
    assert events[-1]["dry_run"]["risk"] == "critical"
    assert events[-1]["dry_run"]["can_execute"] is False


def test_safe_tool_timeout_retries_once_and_records_attempt(tmp_path):
    calls = []

    class TimeoutExecutor:
        def execute(self, capability_name, arguments):
            calls.append((capability_name, arguments))
            return type(
                "Result",
                (),
                {
                    "ok": False,
                    "message": "tool timed out",
                    "error_code": "timeout",
                    "retry_safe": True,
                    "data": None,
                },
            )()

    class ToolPlanner:
        def create_plan(self, user_input, context=None):
            return {
                "mode": "action",
                "capability": "local.echo",
                "arguments": {"text": "hello"},
            }

    repository = RecoveryRepository(tmp_path / "recovery.jsonl")
    agent = AssistantAgent(
        planner=ToolPlanner(),
        executor=TimeoutExecutor(),
        policy_decider=lambda capability: "allow",
        recovery_engine=RecoveryEngine(repository=repository),
    )

    response = agent.handle("execute a tool local.echo")

    assert response["ok"] is False
    assert len(calls) == 2
    assert "tempo limite" in response["message"].lower()
    events = read_recovery_events(repository)
    assert events[0]["event"]["failure_type"] == "timeout"
    attempts = [item for item in events if item["record_type"] == "recovery_attempt"]
    assert len(attempts) == 1
    assert attempts[0]["attempt"]["attempt"] == 1
    assert attempts[0]["attempt"]["succeeded"] is False


def test_policy_block_suggests_safe_alternative_without_executor_call(tmp_path):
    calls = []

    class RecordingExecutor:
        def execute(self, capability_name, arguments):
            calls.append((capability_name, arguments))
            raise AssertionError("blocked policy must not call executor")

    agent, repository = build_agent(tmp_path, executor=RecordingExecutor())

    response = agent.handle(
        "apague todos os arquivos .tmp da pasta atual sem perguntar"
    )

    assert calls == []
    assert response["ok"] is False
    assert "alternativa" in response["message"].lower()
    event = read_recovery_events(repository)[-1]
    assert event["event"]["failure_type"] == "policy_blocked"
    assert event["plan"]["strategy"] == "suggest_safe_alternative"


def test_new_environment_intent_replaces_pending_file_context(tmp_path):
    memory = SessionMemory()
    memory.set_pending_clarification(
        {
            "field": "path",
            "question": "Qual arquivo devo editar?",
            "action": {
                "capability": "write_file",
                "arguments": {"content": "old", "write_mode": "replace"},
            },
            "options": [],
            "accept_free_text": True,
        }
    )
    confirmations = []
    agent, _ = build_agent(
        tmp_path,
        memory=memory,
        confirmer=lambda capability, arguments: confirmations.append(
            (capability, arguments)
        )
        or False,
    )

    response = agent.handle(
        "configure uma variavel de ambiente chamada TESTE_ARGOS com valor 123"
    )

    assert confirmations == [
        (
            "modify_environment_variable",
            {"name": "TESTE_ARGOS", "value": "123", "scope": "user"},
        )
    ]
    assert response["ok"] is False
    assert memory.snapshot()["context"]["pending_clarification"] is None
    assert "caminho" not in response["message"].lower()


def test_create_file_intent_generates_confirmation_and_dry_run(tmp_path):
    target = tmp_path / "teste.txt"
    agent, _ = build_agent(tmp_path)

    response = agent.handle("crie um arquivo chamado teste.txt")

    assert response["status"] == "waiting_confirmation"
    assert response["confirmation"]["capability"] == "create_file"
    assert response["confirmation"]["arguments"]["path"] == str(target)
    assert response["confirmation"]["dry_run"]["action"] == "create_file"
    assert not target.exists()
    assert "abriu" not in response["message"].lower()


def test_path_change_is_sensitive_and_never_opens_cmd(tmp_path):
    calls = []

    class RecordingExecutor:
        def execute(self, capability_name, arguments):
            calls.append((capability_name, arguments))
            return type(
                "Result",
                (),
                {"ok": True, "message": "unexpected", "data": None},
            )()

    agent, _ = build_agent(tmp_path, executor=RecordingExecutor())

    response = agent.handle("adicione C:\\meu-app ao PATH do Windows")

    assert response["status"] == "waiting_confirmation"
    assert response["confirmation"]["capability"] == "modify_path"
    assert response["confirmation"]["dry_run"]["risk"] == "high"
    assert response["confirmation"]["dry_run"]["requires_confirmation"] is True
    assert calls == []
    assert response["confirmation"]["capability"] != "open_application"
