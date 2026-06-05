# Local AI Desktop Assistant MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows-first Python CLI assistant that uses Ollama with a local Qwen3 model, supports safe local actions, session memory, local skills, and a minimal MCP adapter.

**Architecture:** The implementation centers on a modular Python package under `src/assistant`, with a thin CLI loop calling an agent core that delegates to planner, capability registry, executor, memory, skills, and MCP integration. The system keeps all machine-side effects behind a single executor with policy checks so future voice or background modes can reuse the same runtime safely.

**Tech Stack:** Python 3.12, `pytest`, `typer`, `rich`, `pydantic`, `httpx`, `pyyaml`

---

## File Structure

Create these files and keep responsibilities narrow:

- `pyproject.toml`: project metadata, dependencies, pytest config, CLI entry point
- `README.md`: local setup, Ollama prerequisite, usage examples
- `src/assistant/__init__.py`: package marker
- `src/assistant/config.py`: config models and environment loading
- `src/assistant/models.py`: shared Pydantic models for requests, plans, actions, policy decisions, and session events
- `src/assistant/cli.py`: Typer app, interactive REPL, slash commands, confirmation prompts
- `src/assistant/agent.py`: top-level orchestration for one user turn
- `src/assistant/planner.py`: prompt building and structured intent-to-plan parsing
- `src/assistant/llm/ollama_client.py`: Ollama HTTP client
- `src/assistant/capabilities/registry.py`: capability definitions and lookup
- `src/assistant/execution/policy.py`: allow, confirm, blocked policy logic
- `src/assistant/execution/executor.py`: action execution for apps, URLs, file search, and optional shell
- `src/assistant/memory/session.py`: in-memory session state and audit log
- `src/assistant/suggestions.py`: follow-up suggestion rules
- `src/assistant/skills/loader.py`: load local skills from disk
- `src/assistant/mcp/client.py`: minimal MCP server adapter
- `skills/sample-productivity/skill.yaml`: sample local skill
- `tests/test_policy.py`: policy tests
- `tests/test_registry.py`: registry tests
- `tests/test_session_memory.py`: memory tests
- `tests/test_skills_loader.py`: skills loader tests
- `tests/test_suggestions.py`: suggestion tests
- `tests/test_planner.py`: planner parsing tests with mocked LLM output
- `tests/test_executor.py`: executor tests with mocked side effects
- `tests/test_agent.py`: orchestration tests
- `tests/test_cli.py`: CLI smoke tests

### Task 1: Bootstrap the project skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/assistant/__init__.py`
- Create: `src/assistant/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing CLI smoke test**

```python
from typer.testing import CliRunner

from assistant.cli import app


def test_cli_starts_and_exits_cleanly():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Local AI Desktop Assistant" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_cli_starts_and_exits_cleanly -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'assistant'` or missing dependency errors.

- [ ] **Step 3: Write the minimal project scaffold**

`pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "local-ai-desktop-assistant"
version = "0.1.0"
description = "Windows-first local AI assistant MVP"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
  "httpx>=0.27.0",
  "pydantic>=2.7.0",
  "pyyaml>=6.0.1",
  "rich>=13.7.1",
  "typer>=0.12.3",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2.0",
]

[project.scripts]
assistant = "assistant.cli:app"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

`src/assistant/__init__.py`

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

`src/assistant/cli.py`

```python
import typer

app = typer.Typer(help="Local AI Desktop Assistant")


@app.callback()
def main() -> None:
    """CLI entry point."""
```

`README.md`

```markdown
# Local AI Desktop Assistant

Local-first Windows assistant MVP built in Python with Ollama.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_cli_starts_and_exits_cleanly -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md src/assistant/__init__.py src/assistant/cli.py tests/test_cli.py
git commit -m "feat: bootstrap assistant project skeleton"
```

### Task 2: Define shared models and session memory

**Files:**
- Create: `src/assistant/models.py`
- Create: `src/assistant/memory/session.py`
- Test: `tests/test_session_memory.py`

- [ ] **Step 1: Write the failing memory test**

```python
from assistant.memory.session import SessionMemory
from assistant.models import AuditEvent, Suggestion


def test_session_memory_tracks_turns_audit_and_suggestions():
    memory = SessionMemory()
    memory.add_user_message("open vscode")
    memory.add_assistant_message("Opening VS Code")
    memory.add_audit_event(AuditEvent(kind="action", message="opened vscode"))
    memory.set_suggestions([Suggestion(text="Open the project folder next")])

    snapshot = memory.snapshot()

    assert snapshot["history"][0]["role"] == "user"
    assert snapshot["history"][1]["role"] == "assistant"
    assert snapshot["audit"][0]["message"] == "opened vscode"
    assert snapshot["suggestions"][0]["text"] == "Open the project folder next"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_memory.py::test_session_memory_tracks_turns_audit_and_suggestions -v`
Expected: FAIL with import errors for `SessionMemory` or `AuditEvent`.

- [ ] **Step 3: Write minimal models and memory implementation**

`src/assistant/models.py`

```python
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class Suggestion(BaseModel):
    text: str


class AuditEvent(BaseModel):
    kind: str
    message: str


class SessionSnapshot(BaseModel):
    history: list[ChatMessage] = Field(default_factory=list)
    audit: list[AuditEvent] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
```

`src/assistant/memory/session.py`

```python
from assistant.models import AuditEvent, ChatMessage, SessionSnapshot, Suggestion


class SessionMemory:
    def __init__(self) -> None:
        self._history: list[ChatMessage] = []
        self._audit: list[AuditEvent] = []
        self._suggestions: list[Suggestion] = []

    def add_user_message(self, content: str) -> None:
        self._history.append(ChatMessage(role="user", content=content))

    def add_assistant_message(self, content: str) -> None:
        self._history.append(ChatMessage(role="assistant", content=content))

    def add_audit_event(self, event: AuditEvent) -> None:
        self._audit.append(event)

    def set_suggestions(self, suggestions: list[Suggestion]) -> None:
        self._suggestions = suggestions

    def snapshot(self) -> dict:
        return SessionSnapshot(
            history=self._history,
            audit=self._audit,
            suggestions=self._suggestions,
        ).model_dump()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_session_memory.py::test_session_memory_tracks_turns_audit_and_suggestions -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/assistant/models.py src/assistant/memory/session.py tests/test_session_memory.py
git commit -m "feat: add shared models and session memory"
```

### Task 3: Build the capability registry and execution policy

**Files:**
- Create: `src/assistant/capabilities/registry.py`
- Create: `src/assistant/execution/policy.py`
- Test: `tests/test_registry.py`
- Test: `tests/test_policy.py`

- [ ] **Step 1: Write the failing registry and policy tests**

```python
from assistant.capabilities.registry import build_default_registry
from assistant.execution.policy import decide_policy


def test_registry_contains_mvp_capabilities():
    registry = build_default_registry()
    capability_names = {item.name for item in registry.list_all()}
    assert "open_application" in capability_names
    assert "open_url" in capability_names
    assert "search_files" in capability_names


def test_policy_requires_confirmation_for_shell_command():
    decision = decide_policy("run_shell_command")
    assert decision == "confirm"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_registry.py tests/test_policy.py -v`
Expected: FAIL because registry and policy modules do not exist.

- [ ] **Step 3: Write the minimal registry and policy code**

`src/assistant/capabilities/registry.py`

```python
from pydantic import BaseModel


class Capability(BaseModel):
    name: str
    description: str


class CapabilityRegistry:
    def __init__(self, capabilities: list[Capability]) -> None:
        self._capabilities = capabilities

    def list_all(self) -> list[Capability]:
        return list(self._capabilities)

    def get(self, name: str) -> Capability | None:
        for capability in self._capabilities:
            if capability.name == name:
                return capability
        return None


def build_default_registry() -> CapabilityRegistry:
    return CapabilityRegistry(
        [
            Capability(name="open_application", description="Open a local application"),
            Capability(name="open_url", description="Open a URL in the browser"),
            Capability(name="search_files", description="Search files in a directory"),
            Capability(name="run_shell_command", description="Run a shell command"),
        ]
    )
```

`src/assistant/execution/policy.py`

```python
AUTO_EXECUTE = {"open_application", "open_url"}
CONFIRM = {"search_files", "run_shell_command", "type_text", "write_file"}
BLOCKED = {"delete_files", "shutdown_system"}


def decide_policy(capability_name: str) -> str:
    if capability_name in AUTO_EXECUTE:
        return "allow"
    if capability_name in CONFIRM:
        return "confirm"
    if capability_name in BLOCKED:
        return "blocked"
    return "confirm"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_registry.py tests/test_policy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/assistant/capabilities/registry.py src/assistant/execution/policy.py tests/test_registry.py tests/test_policy.py
git commit -m "feat: add capability registry and execution policy"
```

### Task 4: Implement the local action executor

**Files:**
- Create: `src/assistant/execution/executor.py`
- Test: `tests/test_executor.py`

- [ ] **Step 1: Write the failing executor tests**

```python
from assistant.execution.executor import ActionExecutor


def test_executor_opens_url_with_launcher(monkeypatch):
    launched = {}

    def fake_open(url: str) -> None:
        launched["url"] = url

    executor = ActionExecutor(open_url_fn=fake_open)
    result = executor.execute("open_url", {"url": "https://example.com"})

    assert result.ok is True
    assert launched["url"] == "https://example.com"


def test_executor_searches_files(monkeypatch, tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    executor = ActionExecutor()

    result = executor.execute(
        "search_files",
        {"root": str(tmp_path), "pattern": "notes.txt"},
    )

    assert result.ok is True
    assert "notes.txt" in result.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_executor.py -v`
Expected: FAIL because `ActionExecutor` is not implemented.

- [ ] **Step 3: Write the minimal executor**

`src/assistant/execution/executor.py`

```python
from dataclasses import dataclass
from pathlib import Path
import webbrowser


@dataclass
class ExecutionResult:
    ok: bool
    message: str


class ActionExecutor:
    def __init__(self, open_url_fn=None) -> None:
        self._open_url = open_url_fn or webbrowser.open

    def execute(self, capability_name: str, args: dict) -> ExecutionResult:
        if capability_name == "open_url":
            url = args["url"]
            self._open_url(url)
            return ExecutionResult(ok=True, message=f"Opened {url}")

        if capability_name == "search_files":
            root = Path(args["root"])
            pattern = args["pattern"]
            matches = [str(path) for path in root.rglob(pattern)]
            return ExecutionResult(ok=True, message="\n".join(matches))

        return ExecutionResult(ok=False, message=f"Unsupported capability: {capability_name}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_executor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/assistant/execution/executor.py tests/test_executor.py
git commit -m "feat: add MVP action executor"
```

### Task 5: Add Ollama integration and planner parsing

**Files:**
- Create: `src/assistant/llm/ollama_client.py`
- Create: `src/assistant/planner.py`
- Test: `tests/test_planner.py`

- [ ] **Step 1: Write the failing planner test**

```python
from assistant.planner import Planner


class FakeOllamaClient:
    def chat(self, messages):
        return {
            "response": '{"mode":"action","capability":"open_url","arguments":{"url":"https://ollama.com"}}'
        }


def test_planner_parses_structured_action_response():
    planner = Planner(llm_client=FakeOllamaClient())
    plan = planner.create_plan("open ollama website")

    assert plan["mode"] == "action"
    assert plan["capability"] == "open_url"
    assert plan["arguments"]["url"] == "https://ollama.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_planner.py::test_planner_parses_structured_action_response -v`
Expected: FAIL because planner or Ollama client is missing.

- [ ] **Step 3: Write the minimal Ollama client and planner**

`src/assistant/llm/ollama_client.py`

```python
import httpx


class OllamaClient:
    def __init__(self, model: str, base_url: str = "http://localhost:11434/api") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    def chat(self, messages: list[dict]) -> dict:
        response = httpx.post(
            f"{self._base_url}/chat",
            json={"model": self._model, "messages": messages, "stream": False},
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        message = payload["message"]["content"]
        return {"response": message}
```

`src/assistant/planner.py`

```python
import json


class Planner:
    def __init__(self, llm_client) -> None:
        self._llm_client = llm_client

    def create_plan(self, user_input: str) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "Return only JSON. "
                    "Use mode=answer for direct answers or mode=action for executable actions."
                ),
            },
            {"role": "user", "content": user_input},
        ]
        response = self._llm_client.chat(messages)
        return json.loads(response["response"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_planner.py::test_planner_parses_structured_action_response -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/assistant/llm/ollama_client.py src/assistant/planner.py tests/test_planner.py
git commit -m "feat: add Ollama client and planner"
```

### Task 6: Implement local skills loading

**Files:**
- Create: `src/assistant/skills/loader.py`
- Create: `skills/sample-productivity/skill.yaml`
- Test: `tests/test_skills_loader.py`

- [ ] **Step 1: Write the failing skills test**

```python
from assistant.skills.loader import load_skills


def test_load_skills_reads_yaml_metadata(tmp_path):
    skill_dir = tmp_path / "skills" / "sample"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "skill.yaml"
    skill_file.write_text(
        "name: sample\n"
        "description: Sample skill\n"
        "triggers:\n"
        "  - summarize\n",
        encoding="utf-8",
    )

    skills = load_skills(tmp_path / "skills")

    assert len(skills) == 1
    assert skills[0]["name"] == "sample"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_skills_loader.py::test_load_skills_reads_yaml_metadata -v`
Expected: FAIL because the loader is missing.

- [ ] **Step 3: Write the loader and sample skill**

`src/assistant/skills/loader.py`

```python
from pathlib import Path

import yaml


def load_skills(skills_root: Path) -> list[dict]:
    skills = []
    if not skills_root.exists():
        return skills

    for skill_file in skills_root.glob("*/skill.yaml"):
        payload = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
        payload["path"] = str(skill_file.parent)
        skills.append(payload)
    return skills
```

`skills/sample-productivity/skill.yaml`

```yaml
name: sample-productivity
description: Helps draft summaries and next-step suggestions.
triggers:
  - summarize
  - next step
permission_profile: advisory
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_skills_loader.py::test_load_skills_reads_yaml_metadata -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/assistant/skills/loader.py skills/sample-productivity/skill.yaml tests/test_skills_loader.py
git commit -m "feat: add local skills loader"
```

### Task 7: Add the minimal MCP adapter

**Files:**
- Create: `src/assistant/mcp/client.py`
- Test: `tests/test_mcp_client.py`

- [ ] **Step 1: Write the failing MCP client test**

```python
from assistant.mcp.client import MCPClient


class FakeTransport:
    def request(self, method: str, payload: dict) -> dict:
        if method == "tools/list":
            return {"tools": [{"name": "search_docs"}]}
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "done"}]}
        raise AssertionError(method)


def test_mcp_client_lists_and_calls_tools():
    client = MCPClient(transport=FakeTransport())

    tools = client.list_tools()
    result = client.call_tool("search_docs", {"query": "ollama"})

    assert tools[0]["name"] == "search_docs"
    assert result["content"][0]["text"] == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mcp_client.py::test_mcp_client_lists_and_calls_tools -v`
Expected: FAIL because the MCP adapter is missing.

- [ ] **Step 3: Write the minimal MCP adapter**

`src/assistant/mcp/client.py`

```python
class MCPClient:
    def __init__(self, transport) -> None:
        self._transport = transport

    def list_tools(self) -> list[dict]:
        response = self._transport.request("tools/list", {})
        return response["tools"]

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self._transport.request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mcp_client.py::test_mcp_client_lists_and_calls_tools -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/assistant/mcp/client.py tests/test_mcp_client.py
git commit -m "feat: add minimal MCP adapter"
```

### Task 8: Implement suggestions and agent orchestration

**Files:**
- Create: `src/assistant/suggestions.py`
- Create: `src/assistant/agent.py`
- Test: `tests/test_suggestions.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write the failing suggestions and agent tests**

```python
from assistant.agent import AssistantAgent
from assistant.models import Suggestion
from assistant.suggestions import build_suggestions


def test_build_suggestions_for_open_url_action():
    suggestions = build_suggestions("open_url", "Opened https://ollama.com")
    assert suggestions == [Suggestion(text="Ask me to open documentation next")]


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

    assert response["message"] == "Opened https://ollama.com"
    assert response["suggestions"][0]["text"] == "Ask me to open documentation next"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_suggestions.py tests/test_agent.py -v`
Expected: FAIL because the agent and suggestion modules are missing.

- [ ] **Step 3: Write the minimal suggestion engine and agent**

`src/assistant/suggestions.py`

```python
from assistant.models import Suggestion


def build_suggestions(capability_name: str, message: str) -> list[Suggestion]:
    if capability_name == "open_url":
        return [Suggestion(text="Ask me to open documentation next")]
    if capability_name == "search_files":
        return [Suggestion(text="Ask me to open one of the matching files next")]
    return [Suggestion(text="Ask me for the next step")]
```

`src/assistant/agent.py`

```python
from assistant.models import AuditEvent
from assistant.memory.session import SessionMemory
from assistant.suggestions import build_suggestions


class AssistantAgent:
    def __init__(self, planner, executor, memory: SessionMemory | None = None) -> None:
        self._planner = planner
        self._executor = executor
        self._memory = memory or SessionMemory()

    def handle(self, user_input: str) -> dict:
        self._memory.add_user_message(user_input)
        plan = self._planner.create_plan(user_input)

        if plan["mode"] == "action":
            result = self._executor.execute(plan["capability"], plan["arguments"])
            self._memory.add_assistant_message(result.message)
            self._memory.add_audit_event(AuditEvent(kind="action", message=result.message))
            suggestions = build_suggestions(plan["capability"], result.message)
            self._memory.set_suggestions(suggestions)
            return {"message": result.message, "suggestions": [item.model_dump() for item in suggestions]}

        answer = plan["content"]
        self._memory.add_assistant_message(answer)
        suggestions = build_suggestions("answer", answer)
        self._memory.set_suggestions(suggestions)
        return {"message": answer, "suggestions": [item.model_dump() for item in suggestions]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_suggestions.py tests/test_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/assistant/suggestions.py src/assistant/agent.py tests/test_suggestions.py tests/test_agent.py
git commit -m "feat: add suggestion engine and agent orchestration"
```

### Task 9: Wire the interactive CLI to the agent

**Files:**
- Modify: `src/assistant/cli.py`
- Create: `src/assistant/config.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing interactive CLI test**

```python
from typer.testing import CliRunner

from assistant.cli import app


def test_cli_chat_command_uses_agent(monkeypatch):
    class FakeAgent:
        def handle(self, user_input: str) -> dict:
            return {
                "message": "Opened https://ollama.com",
                "suggestions": [{"text": "Ask me to open documentation next"}],
            }

    monkeypatch.setattr("assistant.cli.build_agent", lambda: FakeAgent())

    runner = CliRunner()
    result = runner.invoke(app, ["chat", "open ollama website"])

    assert result.exit_code == 0
    assert "Opened https://ollama.com" in result.stdout
    assert "Ask me to open documentation next" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_cli_chat_command_uses_agent -v`
Expected: FAIL because the `chat` command and `build_agent` factory are missing.

- [ ] **Step 3: Write the minimal CLI wiring**

`src/assistant/config.py`

```python
from pydantic import BaseModel


class AppConfig(BaseModel):
    model: str = "qwen3:8b"
    ollama_base_url: str = "http://localhost:11434/api"
```

`src/assistant/cli.py`

```python
import typer
from rich.console import Console

from assistant.agent import AssistantAgent
from assistant.config import AppConfig
from assistant.execution.executor import ActionExecutor
from assistant.llm.ollama_client import OllamaClient
from assistant.planner import Planner

app = typer.Typer(help="Local AI Desktop Assistant")
console = Console()


def build_agent() -> AssistantAgent:
    config = AppConfig()
    planner = Planner(OllamaClient(model=config.model, base_url=config.ollama_base_url))
    executor = ActionExecutor()
    return AssistantAgent(planner=planner, executor=executor)


@app.command()
def chat(prompt: str) -> None:
    agent = build_agent()
    result = agent.handle(prompt)
    console.print(result["message"])
    for suggestion in result["suggestions"]:
        console.print(f"- {suggestion['text']}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_cli_chat_command_uses_agent -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/assistant/config.py src/assistant/cli.py tests/test_cli.py
git commit -m "feat: wire CLI to assistant runtime"
```

### Task 10: Run the MVP verification sweep and document usage

**Files:**
- Modify: `README.md`
- Test: `tests/test_cli.py`
- Test: `tests/test_agent.py`
- Test: `tests/test_executor.py`
- Test: `tests/test_mcp_client.py`
- Test: `tests/test_planner.py`
- Test: `tests/test_policy.py`
- Test: `tests/test_registry.py`
- Test: `tests/test_session_memory.py`
- Test: `tests/test_skills_loader.py`
- Test: `tests/test_suggestions.py`

- [ ] **Step 1: Extend the README with setup and usage**

```markdown
## Requirements

- Python 3.12
- Ollama running locally
- A local model such as `qwen3:8b`

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
ollama pull qwen3:8b
```

## Usage

```bash
assistant chat "open ollama website"
assistant chat "summarize what an MCP server is"
```
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: PASS for all tests in `tests/`

- [ ] **Step 3: Run the CLI manually against the local model**

Run: `assistant chat "open ollama website"`
Expected: The CLI prints an execution result and at least one next-step suggestion.

- [ ] **Step 4: Commit the verified MVP baseline**

```bash
git add README.md tests
git commit -m "docs: finalize MVP setup and verification flow"
```
