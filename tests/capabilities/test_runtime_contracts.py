from assistant.agent import AssistantAgent
from assistant.capabilities.registry import build_default_registry
from assistant.execution.executor import ActionExecutor
from assistant.execution.policy import decide_policy
from assistant.files.path_resolver import PathResolver
from assistant.memory.session import SessionMemory
from assistant.planner import Planner
from assistant.recovery.dry_run import DryRunBuilder


class FailIfCalledClient:
    def chat(self, messages):
        raise AssertionError("deterministic planner path must not call the model")


class StaticPlanner:
    def __init__(self, plan):
        self._plan = plan

    def create_plan(self, user_input, context=None):
        return self._plan


class FailIfCalledExecutor:
    def execute(self, capability_name, arguments):
        raise AssertionError("invalid action must not reach the executor")


def build_memory(tmp_path):
    memory = SessionMemory()
    memory.set_context(
        current_cwd=str(tmp_path),
        default_search_root=str(tmp_path),
        user_home=str(tmp_path),
    )
    return memory


def test_registry_is_source_of_truth_for_canonical_file_actions():
    registry = build_default_registry()

    assert registry.resolve("create_file").name == "file.create"
    assert registry.resolve("write_file").name == "file.write"
    assert registry.resolve("read_file").name == "file.read"
    assert registry.resolve("open_file").name == "file.open"
    assert registry.resolve("create_directory").name == "file.create_directory"
    assert registry.resolve("search_files").name == "files.search"
    assert registry.resolve("file.delete_many").name == "file.delete_dry_run"
    assert registry.resolve("shell.run") is None


def test_unknown_capability_dry_run_is_not_executable():
    plan = DryRunBuilder(build_default_registry()).build(
        "does.not.exist",
        {},
    )

    assert plan.can_execute is False
    assert plan.error_code == "unsupported_capability"
    assert plan.requires_confirmation is False


def test_unsupported_capability_never_reaches_confirmation(tmp_path):
    agent = AssistantAgent(
        planner=StaticPlanner(
            {
                "mode": "action",
                "capability": "does.not.exist",
                "arguments": {},
            }
        ),
        executor=FailIfCalledExecutor(),
        memory=build_memory(tmp_path),
        capability_registry=build_default_registry(),
    )

    response = agent.handle("execute")

    assert response["status"] == "completed"
    assert response["ok"] is False
    assert response["error_code"] == "unsupported_capability"
    assert "confirmation" not in response


def test_invalid_write_schema_never_reaches_confirmation(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("existing", encoding="utf-8")
    agent = AssistantAgent(
        planner=StaticPlanner(
            {
                "mode": "action",
                "capability": "write_file",
                "arguments": {"path": str(target), "content": "new"},
            }
        ),
        executor=FailIfCalledExecutor(),
        memory=build_memory(tmp_path),
        capability_registry=build_default_registry(),
    )

    response = agent.handle("write")

    assert response["status"] == "completed"
    assert response["ok"] is False
    assert response["error_code"] == "invalid_schema"
    assert "mode" in response["message"]
    assert "confirmation" not in response


def test_empty_file_write_defaults_to_overwrite(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("", encoding="utf-8")
    agent = AssistantAgent(
        planner=StaticPlanner(
            {
                "mode": "action",
                "capability": "write_file",
                "arguments": {"path": str(target), "content": "new"},
            }
        ),
        executor=ActionExecutor(),
        memory=build_memory(tmp_path),
        capability_registry=build_default_registry(),
        confirmer=lambda capability, arguments: True,
    )

    response = agent.handle("write")

    assert response["ok"] is True
    assert target.read_text(encoding="utf-8") == "new"


def test_path_resolver_uses_current_cwd_for_context_markers_and_relative_paths(
    tmp_path,
):
    resolver = PathResolver()
    context = {"current_cwd": str(tmp_path)}

    assert resolver.resolve("aqui", context) == tmp_path.resolve()
    assert resolver.resolve("nesta pasta", context) == tmp_path.resolve()
    assert resolver.resolve("docs\\notes.txt", context) == (
        tmp_path / "docs" / "notes.txt"
    ).resolve()


def test_planner_routes_create_read_open_and_search_deterministically(tmp_path):
    planner = Planner(llm_client=FailIfCalledClient())
    context = {"current_cwd": str(tmp_path)}

    assert planner.create_plan(
        "crie uma pasta chamada docs",
        context=context,
    )["capability"] == "file.create_directory"
    assert planner.create_plan(
        "leia o arquivo teste.txt",
        context=context,
    ) == {
        "mode": "action",
        "capability": "file.read",
        "arguments": {"path": "teste.txt"},
    }
    assert planner.create_plan(
        "abra o arquivo teste.txt",
        context=context,
    ) == {
        "mode": "action",
        "capability": "file.open",
        "arguments": {"path": "teste.txt"},
    }
    assert planner.create_plan(
        "buscar arquivos txt nesta pasta",
        context=context,
    ) == {
        "mode": "action",
        "capability": "files.search",
        "arguments": {
            "root": str(tmp_path),
            "pattern": "*.txt",
            "max_results": 5,
        },
    }


def test_delete_dry_run_lists_candidates_without_deleting(tmp_path):
    first = tmp_path / "one.tmp"
    second = tmp_path / "two.tmp"
    first.write_text("keep", encoding="utf-8")
    second.write_text("keep", encoding="utf-8")

    result = ActionExecutor().execute(
        "file.delete_dry_run",
        {"path": str(tmp_path), "pattern": "*.tmp"},
    )

    assert result.ok is True
    assert result.data["candidates"] == [str(first), str(second)]
    assert first.exists()
    assert second.exists()


def test_delete_current_directory_is_blocked_before_confirmation(tmp_path):
    agent = AssistantAgent(
        planner=Planner(llm_client=FailIfCalledClient()),
        executor=FailIfCalledExecutor(),
        memory=build_memory(tmp_path),
        capability_registry=build_default_registry(),
    )

    response = agent.handle("apague a pasta atual")

    assert response["ok"] is False
    assert response["error_code"] == "policy_blocked"
    assert "confirmation" not in response


def test_policy_uses_canonical_capability_contracts():
    registry = build_default_registry()

    assert decide_policy("files.search", registry=registry) == "allow"
    assert decide_policy("file.read", registry=registry) == "allow"
    assert decide_policy("file.delete_dry_run", registry=registry) == "allow"
    assert decide_policy("file.create", registry=registry) == "confirm"
    assert decide_policy("file.move_many", registry=registry) == "confirm"
    assert decide_policy("file.delete_one", registry=registry) == "confirm"
    assert decide_policy("does.not.exist", registry=registry) == "blocked"


def test_shell_request_is_unsupported_without_confirmation(tmp_path):
    agent = AssistantAgent(
        planner=Planner(llm_client=FailIfCalledClient()),
        executor=FailIfCalledExecutor(),
        memory=build_memory(tmp_path),
        capability_registry=build_default_registry(),
    )

    response = agent.handle("rode o comando dir")

    assert response["ok"] is False
    assert response["error_code"] == "unsupported_capability"
    assert "confirmation" not in response


def test_move_txt_files_is_not_confused_with_path_environment(tmp_path):
    planner = Planner(llm_client=FailIfCalledClient())

    plan = planner.create_plan(
        "mova os arquivos .txt para a pasta backup",
        context={"current_cwd": str(tmp_path)},
    )

    assert plan == {
        "mode": "action",
        "capability": "file.move_many",
        "arguments": {
            "source_root": str(tmp_path),
            "pattern": "*.txt",
            "destination": "backup",
        },
    }


def test_executor_returns_structured_not_found():
    result = ActionExecutor().execute(
        "file.read",
        {"path": "Z:\\definitely-missing\\notes.txt"},
    )

    assert result.ok is False
    assert result.error_code == "not_found"


def test_agent_returns_structured_execution_failed(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")

    def fail_to_open(path):
        raise OSError("launcher failed")

    agent = AssistantAgent(
        planner=StaticPlanner(
            {
                "mode": "action",
                "capability": "file.open",
                "arguments": {"path": str(target)},
            }
        ),
        executor=ActionExecutor(open_file_fn=fail_to_open),
        memory=build_memory(tmp_path),
        capability_registry=build_default_registry(),
    )

    response = agent.handle("open")

    assert response["ok"] is False
    assert response["error_code"] == "execution_failed"


def test_agent_converts_executor_exception_to_structured_error(tmp_path):
    class BrokenExecutor:
        def execute(self, capability_name, arguments):
            raise RuntimeError("unexpected executor failure")

    agent = AssistantAgent(
        planner=StaticPlanner(
            {
                "mode": "action",
                "capability": "file.read",
                "arguments": {"path": str(tmp_path / "notes.txt")},
            }
        ),
        executor=BrokenExecutor(),
        memory=build_memory(tmp_path),
        capability_registry=build_default_registry(),
    )

    response = agent.handle("read")

    assert response["ok"] is False
    assert response["error_code"] == "execution_failed"
    assert "unexpected executor failure" in response["message"]
