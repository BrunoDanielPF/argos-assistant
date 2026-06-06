from assistant.agent import AssistantAgent


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
