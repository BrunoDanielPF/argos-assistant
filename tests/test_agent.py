from assistant.agent import AssistantAgent
from assistant.execution.executor import ActionExecutor
from assistant.files.resolver import FileResolver
from assistant.memory.models import (
    MemoryCandidate,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
)
from assistant.memory.session import SessionMemory
from assistant.planner import Planner
from assistant.recovery.engine import RecoveryEngine


class FakePlanner:
    def create_plan(self, user_input: str) -> dict:
        return {
            "mode": "action",
            "capability": "open_url",
            "arguments": {"url": "https://ollama.com"},
        }


class FakeExecutor:
    def execute(self, capability_name: str, args: dict):
        return type("Result", (), {"ok": True, "message": "Opened https://ollama.com"})()


def test_agent_executes_action_and_returns_suggestions():
    agent = AssistantAgent(planner=FakePlanner(), executor=FakeExecutor())

    response = agent.handle("open ollama website")

    assert response["ok"] is True
    assert response["message"] == "Opened https://ollama.com"
    assert response["suggestions"][0]["text"] == "Ask me to open documentation next"


def test_agent_blocks_forbidden_capability():
    class FakeBlockedPlanner:
        def create_plan(self, user_input: str) -> dict:
            return {
                "mode": "action",
                "capability": "delete_files",
                "arguments": {"path": "C:\\temp"},
            }

    class FailIfCalledExecutor:
        def execute(self, capability_name: str, args: dict):
            raise AssertionError("executor should not run for blocked capability")

    agent = AssistantAgent(
        planner=FakeBlockedPlanner(),
        executor=FailIfCalledExecutor(),
    )

    response = agent.handle("delete files")

    assert response["ok"] is False
    assert "Blocked capability" in response["message"]


def test_agent_requires_confirmation_before_sensitive_action():
    class FakeConfirmPlanner:
        def create_plan(self, user_input: str) -> dict:
            return {
                "mode": "action",
                "capability": "search_files",
                "arguments": {"root": "C:\\temp", "pattern": "notes.txt"},
            }

    confirmations = []

    def fake_confirm(capability_name: str, arguments: dict) -> bool:
        confirmations.append((capability_name, arguments))
        return False

    class FailIfCalledExecutor:
        def execute(self, capability_name: str, args: dict):
            raise AssertionError("executor should not run when confirmation is denied")

    agent = AssistantAgent(
        planner=FakeConfirmPlanner(),
        executor=FailIfCalledExecutor(),
        confirmer=fake_confirm,
    )

    response = agent.handle("search notes")

    assert response["ok"] is False
    assert response["message"] == "Action cancelled by user"
    assert confirmations == [("search_files", {"root": "C:\\temp", "pattern": "notes.txt"})]


def test_agent_without_confirmer_requests_confirmation_instead_of_cancelling():
    class ConfirmPlanner:
        def create_plan(self, user_input: str) -> dict:
            return {
                "mode": "action",
                "capability": "create_file",
                "arguments": {
                    "path": "C:\\Users\\frand\\receita.md",
                    "content": "receita",
                },
            }

    class FailIfCalledExecutor:
        def execute(self, capability_name: str, args: dict):
            raise AssertionError("executor should wait for confirmation")

    agent = AssistantAgent(
        planner=ConfirmPlanner(),
        executor=FailIfCalledExecutor(),
    )

    response = agent.handle("crie o arquivo")

    assert response["status"] == "waiting_confirmation"
    assert response["confirmation"]["capability"] == "create_file"
    assert response["confirmation"]["arguments"]["path"].endswith("receita.md")
    assert "cancel" not in response["message"].lower()
    audit = agent.memory.snapshot()["audit"][-1]
    assert audit["capability"] == "create_file"
    assert audit["policy"] == "confirm"
    assert audit["decision"] == "pending"


def test_agent_executes_action_after_remote_confirmation():
    executed = []

    class RecordingExecutor:
        def execute(self, capability_name: str, args: dict):
            executed.append((capability_name, args))
            return type(
                "Result",
                (),
                {"ok": True, "message": "Arquivo criado", "data": None},
            )()

    agent = AssistantAgent(planner=FakePlanner(), executor=RecordingExecutor())

    response = agent.execute_confirmed_action(
        "create_file",
        {"path": "C:\\Users\\frand\\receita.md", "content": "receita"},
        approved=True,
    )

    assert response["ok"] is True
    assert response["status"] == "completed"
    assert executed[0][0] == "create_file"


class FakeFailedExecutor:
    def execute(self, capability_name: str, args: dict):
        return type("Result", (), {"ok": False, "message": "Failed to open https://ollama.com"})()


def test_agent_returns_failed_action_with_ok_false():
    agent = AssistantAgent(planner=FakePlanner(), executor=FakeFailedExecutor())

    response = agent.handle("open ollama website")

    assert response["ok"] is False
    assert response["message"] == "Failed to open https://ollama.com"
    assert response["suggestions"][0]["text"] == "Ask me to open documentation next"


class FakeAnswerPlanner:
    def create_plan(self, user_input: str) -> dict:
        return {"mode": "answer", "content": "Here is a direct answer"}


def test_agent_returns_answer_mode_response():
    agent = AssistantAgent(planner=FakeAnswerPlanner(), executor=FakeExecutor())

    response = agent.handle("what should I do next?")

    assert response["ok"] is True
    assert response["message"] == "Here is a direct answer"
    assert response["suggestions"][0]["text"] == "Ask me for the next step"


def test_agent_stores_last_search_results_after_search():
    class FakeSearchPlanner:
        def create_plan(self, user_input: str) -> dict:
            return {
                "mode": "action",
                "capability": "search_files",
                "arguments": {"root": "C:\\workspace", "pattern": "README.md"},
            }

    class FakeSearchExecutor:
        def execute(self, capability_name: str, args: dict):
            return type(
                "Result",
                (),
                {
                    "ok": True,
                    "message": "Found 1 match for 'README.md':\n- C:\\workspace\\README.md",
                    "data": {"matches": ["C:\\workspace\\README.md"], "all_count": 1},
                },
            )()

    agent = AssistantAgent(
        planner=FakeSearchPlanner(),
        executor=FakeSearchExecutor(),
        confirmer=lambda capability_name, arguments: True,
    )

    response = agent.handle("find README.md")

    assert response["ok"] is True
    assert agent.memory.snapshot()["context"]["last_search_results"] == [
        "C:\\workspace\\README.md"
    ]


def test_agent_injects_relevant_long_term_memories_into_context():
    class ContextPlanner:
        def __init__(self) -> None:
            self.context = None

        def create_plan(self, user_input: str, context: dict | None = None) -> dict:
            self.context = context
            return {"mode": "answer", "content": "Resposta objetiva"}

    class FakeLongTermMemory:
        def search(self, query: str, max_results: int = 5) -> list[dict]:
            return [
                {
                    "learning": "O usuario prefere respostas objetivas em portugues.",
                    "context": "preferencias",
                    "source_file": "correcoes.md",
                }
            ]

    planner = ContextPlanner()
    agent = AssistantAgent(
        planner=planner,
        executor=FakeExecutor(),
        long_term_memory=FakeLongTermMemory(),
    )

    response = agent.handle("como devo responder?")

    assert response["ok"] is True
    assert planner.context["long_term_memories"] == [
        {
            "learning": "O usuario prefere respostas objetivas em portugues.",
            "context": "preferencias",
            "source_file": "correcoes.md",
        }
    ]


def test_agent_retrieves_and_observes_with_memory_engine():
    class ContextPlanner:
        def __init__(self) -> None:
            self.context = None

        def create_plan(self, user_input: str, context: dict | None = None) -> dict:
            self.context = context
            return {"mode": "answer", "content": "Resposta objetiva"}

    class FakeMemoryEngine:
        def __init__(self) -> None:
            self.observed = None

        def retrieve(self, query: str, context: dict) -> list[MemoryRecord]:
            candidate = MemoryCandidate(
                type=MemoryType.USER_PREFERENCE,
                content="O usuario prefere respostas objetivas.",
                scope="user",
            )
            return [
                MemoryRecord(
                    type=candidate.type,
                    status=MemoryStatus.ACTIVE,
                    content=candidate.content,
                    scope=candidate.scope,
                    importance=candidate.importance,
                    confidence=candidate.confidence,
                    source=candidate.source,
                    observed_at=candidate.observed_at,
                )
            ]

        def observe(
            self,
            user_input: str,
            assistant_response: str,
            context: dict,
        ) -> list:
            self.observed = (user_input, assistant_response, context)
            return []

    planner = ContextPlanner()
    memory_engine = FakeMemoryEngine()
    agent = AssistantAgent(
        planner=planner,
        executor=FakeExecutor(),
        memory_engine=memory_engine,
    )

    response = agent.handle("como devo responder?")

    assert response["ok"] is True
    assert planner.context["long_term_memories"][0]["learning"] == (
        "O usuario prefere respostas objetivas."
    )
    assert planner.context["long_term_memories"][0]["memory_type"] == (
        "user_preference"
    )
    assert memory_engine.observed[0:2] == (
        "como devo responder?",
        "Resposta objetiva",
    )


def test_agent_injects_previous_conversation_into_planner_context():
    class ContextPlanner:
        def __init__(self) -> None:
            self.contexts = []

        def create_plan(self, user_input: str, context: dict | None = None) -> dict:
            self.contexts.append(context)
            answer = "2 + 2 = 4" if len(self.contexts) == 1 else "4 + 4 = 8"
            return {"mode": "answer", "content": answer}

    planner = ContextPlanner()
    agent = AssistantAgent(planner=planner, executor=FakeExecutor())

    agent.handle("quanto e 2 + 2?")
    agent.handle("e 4 + 4?")

    assert planner.contexts[0]["conversation_history"] == []
    assert planner.contexts[1]["conversation_history"] == [
        {"role": "user", "content": "quanto e 2 + 2?"},
        {"role": "assistant", "content": "2 + 2 = 4"},
    ]


def test_agent_executes_confirmed_multi_step_plan():
    class MultiStepPlanner:
        def create_plan(self, user_input: str) -> dict:
            return {
                "mode": "plan",
                "steps": [
                    {
                        "capability": "create_file",
                        "arguments": {"path": "C:\\Users\\frand\\hello_world.md", "content": "hello world"},
                    },
                    {
                        "capability": "open_file",
                        "arguments": {"path": "C:\\Users\\frand\\hello_world.md"},
                    },
                ],
            }

    executed = []

    class RecordingExecutor:
        def execute(self, capability_name: str, args: dict):
            executed.append((capability_name, args))
            return type("Result", (), {"ok": True, "message": f"Executed {capability_name}", "data": None})()

    confirmations = []

    def confirm(capability_name: str, arguments: dict) -> bool:
        confirmations.append((capability_name, arguments))
        return True

    agent = AssistantAgent(
        planner=MultiStepPlanner(),
        executor=RecordingExecutor(),
        confirmer=confirm,
    )

    response = agent.handle("crie arquivo")

    assert response["ok"] is True
    assert "Executed create_file" in response["message"]
    assert "Executed open_file" in response["message"]
    assert [item[0] for item in executed] == ["create_file", "open_file"]
    assert [item[0] for item in confirmations] == ["create_file"]


def test_agent_suggests_file_creation_when_open_file_fails_missing():
    class MissingFilePlanner:
        def create_plan(self, user_input: str) -> dict:
            return {
                "mode": "action",
                "capability": "open_file",
                "arguments": {"path": "C:\\Users\\frand\\hello_world.md"},
            }

    class MissingFileExecutor:
        def execute(self, capability_name: str, args: dict):
            return type(
                "Result",
                (),
                {
                    "ok": False,
                    "message": "File not found: C:\\Users\\frand\\hello_world.md",
                    "data": None,
                },
            )()

    agent = AssistantAgent(planner=MissingFilePlanner(), executor=MissingFileExecutor())

    response = agent.handle("abra arquivo")

    assert response["ok"] is False
    assert "File not found" in response["message"]
    assert "Posso criar esse arquivo" in response["message"]


def test_agent_stores_planner_clarification_in_session():
    pending = {
        "field": "write_mode",
        "question": "Substituir ou adicionar?",
        "action": {
            "capability": "write_file",
            "arguments": {"path": "hello_world", "content": "ola mundo bruno"},
        },
        "options": [
            {"id": "replace", "label": "substituir"},
            {"id": "append", "label": "adicionar"},
        ],
    }

    class ClarificationPlanner:
        def create_plan(self, user_input: str, context: dict | None = None) -> dict:
            return {
                "mode": "clarification",
                "question": "Substituir ou adicionar?",
                "pending": pending,
            }

    agent = AssistantAgent(planner=ClarificationPlanner(), executor=FakeExecutor())

    response = agent.handle("edite o arquivo")

    assert response["ok"] is True
    assert response["message"] == "Substituir ou adicionar?"
    assert agent.memory.snapshot()["context"]["pending_clarification"] == pending


def test_agent_drops_pending_clarification_when_user_changes_subject():
    calls = []

    class ContextPlanner:
        def create_plan(self, user_input: str, context: dict | None = None) -> dict:
            calls.append((user_input, context))
            return {
                "mode": "answer",
                "content": "Vamos planejar a trilha de domingo.",
            }

    memory = SessionMemory()
    memory.set_pending_clarification(
        {
            "field": "project_type",
            "question": "Qual tipo de projeto?",
            "action": {
                "capability": "user.project_scaffold",
                "arguments": {"project_type": "web"},
            },
            "options": [
                {"id": "web", "label": "Web"},
                {"id": "mobile", "label": "Mobile"},
            ],
        }
    )

    agent = AssistantAgent(
        planner=ContextPlanner(),
        executor=FakeExecutor(),
        memory=memory,
    )

    response = agent.handle(
        "esquece, quero me ajude a como planejar fazer uma trilha em um domingo"
    )

    assert response["ok"] is True
    assert "trilha" in response["message"].lower()
    assert calls[0][1]["pending_clarification"] is None
    assert calls[0][1]["conversation_history"] == []
    assert agent.memory.snapshot()["context"]["pending_clarification"] is None


def test_agent_resolves_file_before_confirmation_and_completes_natural_clarification(tmp_path):
    target = tmp_path / "hello_world.md"
    target.write_text("hello world", encoding="utf-8")
    confirmations = []

    def confirm(capability_name: str, arguments: dict) -> bool:
        confirmations.append((capability_name, dict(arguments)))
        return True

    memory = SessionMemory()
    memory.set_context(
        current_cwd=str(tmp_path),
        default_search_root=str(tmp_path),
        user_home=str(tmp_path),
    )
    planner = Planner(llm_client=FailIfCalledClientForAgent())
    agent = AssistantAgent(
        planner=planner,
        executor=ActionExecutor(),
        memory=memory,
        confirmer=confirm,
        file_resolver=FileResolver(),
    )

    clarification = agent.handle(
        "preciso editar um arquivo hello_world colocando de texto ola mundo bruno nesse arquivo"
    )
    result = agent.handle("adicione no final sem apagar o que existe")

    assert clarification["ok"] is True
    assert "adicionar" in clarification["message"].lower()
    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "hello world\nola mundo bruno"
    assert confirmations == [
        (
            "write_file",
            {
                "path": str(target.resolve()),
                "content": "ola mundo bruno",
                "write_mode": "append",
            },
        )
    ]
    assert agent.memory.snapshot()["context"]["pending_clarification"] is None


def test_agent_asks_user_to_choose_when_file_resolution_is_ambiguous(tmp_path):
    (tmp_path / "hello_world.md").write_text("markdown", encoding="utf-8")
    (tmp_path / "hello_world.txt").write_text("text", encoding="utf-8")
    memory = SessionMemory()
    memory.set_context(current_cwd=str(tmp_path), user_home=str(tmp_path))

    class WritePlanner:
        def create_plan(self, user_input: str, context: dict | None = None) -> dict:
            return {
                "mode": "action",
                "capability": "write_file",
                "arguments": {
                    "path": "hello_world",
                    "content": "novo",
                    "write_mode": "replace",
                },
            }

    agent = AssistantAgent(
        planner=WritePlanner(),
        executor=ActionExecutor(),
        memory=memory,
        confirmer=lambda capability, arguments: True,
        file_resolver=FileResolver(),
    )

    response = agent.handle("substitua")

    assert response["ok"] is True
    assert "mais de um arquivo" in response["message"].lower()
    pending = agent.memory.snapshot()["context"]["pending_clarification"]
    assert pending["field"] == "path"
    assert len(pending["options"]) == 3


def test_agent_converts_write_to_create_for_explicit_new_file(tmp_path):
    target = tmp_path / "receita.md"
    confirmations = []

    class WritePlanner:
        def create_plan(self, user_input, context=None):
            return {
                "mode": "action",
                "capability": "write_file",
                "arguments": {
                    "path": str(target),
                    "content": "# Receita",
                    "write_mode": "replace",
                },
            }

    agent = AssistantAgent(
        planner=WritePlanner(),
        executor=ActionExecutor(),
        confirmer=lambda capability, arguments: confirmations.append(
            (capability, arguments)
        )
        or True,
    )

    response = agent.handle("salve a receita neste arquivo")

    assert response["ok"] is True
    assert target.read_text(encoding="utf-8") == "# Receita"
    assert confirmations[0][0] == "create_file"


def test_agent_converts_write_without_mode_to_create_for_explicit_new_file(tmp_path):
    target = tmp_path / "receita.md"
    confirmations = []

    class WritePlanner:
        def create_plan(self, user_input, context=None):
            return {
                "mode": "action",
                "capability": "write_file",
                "arguments": {
                    "path": str(target),
                    "content": "# Receita",
                },
            }

    agent = AssistantAgent(
        planner=WritePlanner(),
        executor=ActionExecutor(),
        confirmer=lambda capability, arguments: confirmations.append(
            (capability, arguments)
        )
        or True,
    )

    response = agent.handle("salve a receita neste arquivo")

    assert response["ok"] is True
    assert target.read_text(encoding="utf-8") == "# Receita"
    assert confirmations[0][0] == "create_file"


def test_agent_returns_dry_run_for_sensitive_confirmation(tmp_path):
    target = tmp_path / "notes.md"

    class CreatePlanner:
        def create_plan(self, user_input: str) -> dict:
            return {
                "mode": "action",
                "capability": "create_file",
                "arguments": {"path": str(target), "content": "hello"},
            }

    agent = AssistantAgent(
        planner=CreatePlanner(),
        executor=ActionExecutor(),
        recovery_engine=RecoveryEngine(),
    )

    response = agent.handle("crie o arquivo")

    assert response["status"] == "waiting_confirmation"
    assert response["confirmation"]["dry_run"]["action"] == "create_file"
    assert response["confirmation"]["dry_run"]["resources_affected"] == [
        str(target)
    ]
    assert not target.exists()


def test_agent_explains_policy_block_without_executing():
    class DeletePlanner:
        def create_plan(self, user_input: str) -> dict:
            return {
                "mode": "action",
                "capability": "delete_files",
                "arguments": {"path": ".", "pattern": "*.tmp"},
            }

    class FailIfCalledExecutor:
        def execute(self, capability_name: str, args: dict):
            raise AssertionError("blocked action must not execute")

    agent = AssistantAgent(
        planner=DeletePlanner(),
        executor=FailIfCalledExecutor(),
        recovery_engine=RecoveryEngine(),
    )

    response = agent.handle(
        "apague todos os arquivos .tmp da pasta atual sem perguntar"
    )

    assert response["ok"] is False
    assert "bloqueada" in response["message"].lower()
    assert "alternativa" in response["message"].lower()


def test_agent_retries_tool_timeout_only_once():
    attempts = []

    class ToolPlanner:
        def create_plan(self, user_input: str) -> dict:
            return {
                "mode": "action",
                "capability": "local.echo",
                "arguments": {"text": "hello"},
            }

    class TimeoutThenSuccessExecutor:
        def execute(self, capability_name: str, args: dict):
            attempts.append((capability_name, args))
            if len(attempts) == 1:
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
            return type(
                "Result",
                (),
                {
                    "ok": True,
                    "message": "Tool local.echo executed successfully",
                    "error_code": None,
                    "retry_safe": True,
                    "data": {"text": "hello"},
                },
            )()

    agent = AssistantAgent(
        planner=ToolPlanner(),
        executor=TimeoutThenSuccessExecutor(),
        policy_decider=lambda capability: "allow",
        recovery_engine=RecoveryEngine(),
    )

    response = agent.handle("execute echo")

    assert response["ok"] is True
    assert len(attempts) == 2


def test_agent_does_not_treat_new_explicit_action_as_pending_file_path():
    calls = []

    class ContextPlanner:
        def create_plan(self, user_input: str, context: dict | None = None) -> dict:
            calls.append(context)
            return {
                "mode": "action",
                "capability": "open_application",
                "arguments": {"application": "calculator"},
            }

    memory = SessionMemory()
    memory.set_pending_clarification(
        {
            "field": "path",
            "question": "Qual arquivo?",
            "action": {
                "capability": "write_file",
                "arguments": {"content": "hello", "write_mode": "replace"},
            },
            "options": [],
            "accept_free_text": True,
        }
    )
    executed = []

    class RecordingExecutor:
        def execute(self, capability_name: str, args: dict):
            executed.append(capability_name)
            return type(
                "Result",
                (),
                {"ok": True, "message": "Opened", "data": None},
            )()

    agent = AssistantAgent(
        planner=ContextPlanner(),
        executor=RecordingExecutor(),
        memory=memory,
    )

    response = agent.handle("abra a calculadora")

    assert response["ok"] is True
    assert calls[0]["pending_clarification"] is None
    assert executed == ["open_application"]


def test_agent_turns_planner_exception_into_recovery_diagnostic():
    class FailedPlanner:
        def create_plan(self, user_input: str) -> dict:
            raise TimeoutError("model timed out")

    agent = AssistantAgent(
        planner=FailedPlanner(),
        executor=FakeExecutor(),
        recovery_engine=RecoveryEngine(),
    )

    response = agent.handle("execute a tarefa")

    assert response["ok"] is False
    assert "tempo limite" in response["message"].lower()


def test_agent_registers_file_context_ambiguity(tmp_path):
    (tmp_path / "notes.md").write_text("one", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("two", encoding="utf-8")
    recorded = []

    class RecordingRecovery:
        def handle_failure(self, **kwargs):
            recorded.append(kwargs)
            return RecoveryEngine().handle_failure(**kwargs)

    class WritePlanner:
        def create_plan(self, user_input: str, context=None) -> dict:
            return {
                "mode": "action",
                "capability": "write_file",
                "arguments": {
                    "path": "notes",
                    "content": "new",
                    "write_mode": "replace",
                },
            }

    memory = SessionMemory()
    memory.set_context(current_cwd=str(tmp_path), user_home=str(tmp_path))
    agent = AssistantAgent(
        planner=WritePlanner(),
        executor=ActionExecutor(),
        memory=memory,
        recovery_engine=RecordingRecovery(),
    )

    response = agent.handle("edite notes")

    assert response["ok"] is True
    assert recorded[0]["error_code"] == "context_ambiguity"
    assert not response.get("confirmation")


class FailIfCalledClientForAgent:
    def chat(self, messages):
        raise AssertionError("LLM should not be called for deterministic clarification")
