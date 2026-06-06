from pathlib import Path
import sys

from assistant.capabilities.registry import build_default_registry
from assistant.agent import AssistantAgent
from assistant.execution.executor import ActionExecutor
from assistant.memory.session import SessionMemory
from assistant.planner import Planner
from assistant.tools.catalog import ToolCatalog
from assistant.tools.runner import ToolRunner
from assistant.tools.state import ToolStateStore


REPO_ROOT = Path(__file__).parents[2]


def bundled_catalog(tmp_path):
    return ToolCatalog(
        tools_root=tmp_path / "user-tools",
        state_store=ToolStateStore(tmp_path / "state.json"),
        bundled_root=REPO_ROOT / "tools",
    )


def test_catalog_exposes_bundled_spring_tool(tmp_path):
    catalog = bundled_catalog(tmp_path)

    assert catalog.get_enabled("local.spring.create_project") is not None


def test_registry_includes_enabled_tool(tmp_path):
    registry = build_default_registry(bundled_catalog(tmp_path))

    assert registry.get("local.spring.create_project") is not None


def test_action_executor_runs_dynamic_tool(tmp_path):
    catalog = bundled_catalog(tmp_path)
    executor = ActionExecutor(
        tool_catalog=catalog,
        tool_runner=ToolRunner(python_executable=sys.executable),
    )

    result = executor.execute(
        "local.spring.create_project",
        {
            "name": "pedidos-api",
            "directory": str(tmp_path),
            "java_version": 21,
            "build_tool": "maven",
            "group_id": "com.example",
        },
    )

    assert result.ok is True
    assert (tmp_path / "pedidos-api" / "pom.xml").exists()


class FailIfModelCalled:
    def chat(self, messages):
        raise AssertionError("deterministic Spring workflow should not call the model")


def test_agent_completes_spring_project_workflow_with_tool(tmp_path):
    catalog = bundled_catalog(tmp_path)
    executor = ActionExecutor(
        tool_catalog=catalog,
        tool_runner=ToolRunner(python_executable=sys.executable),
    )
    memory = SessionMemory()
    memory.set_context(
        current_cwd=str(tmp_path),
        default_search_root=str(tmp_path),
        user_home=str(tmp_path),
    )
    confirmations = []
    agent = AssistantAgent(
        planner=Planner(FailIfModelCalled()),
        executor=executor,
        memory=memory,
        policy_decider=lambda capability: (
            "confirm" if catalog.get_enabled(capability) else "blocked"
        ),
        confirmer=lambda capability, arguments: confirmations.append(
            (capability, arguments)
        )
        or True,
    )

    prompts = [
        "quero criar um app backend com java e estruturar os arquivos iniciais",
        "vamos usar spring boot",
        "pedidos-api",
        "java 21",
        "maven",
        "com.example",
    ]
    result = None
    for prompt in prompts:
        result = agent.handle(prompt)

    assert result["ok"] is True
    assert (tmp_path / "pedidos-api" / "pom.xml").exists()
    assert confirmations[0][0] == "local.spring.create_project"
