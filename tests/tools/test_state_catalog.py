import json
from pathlib import Path

import pytest
import yaml

from assistant.tools.catalog import ToolCatalog
from assistant.tools.state import InvalidToolTransition, ToolStateStore, hash_tool_files

from tests.tools.test_sdk_foundation import valid_manifest


def create_installed_tool(root: Path, name: str = "local.echo", version: str = "1.0.0") -> Path:
    tool_dir = root / name / version
    tool_dir.mkdir(parents=True)
    payload = valid_manifest()
    payload["name"] = name
    payload["version"] = version
    (tool_dir / "tool.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )
    (tool_dir / "handler.py").write_text(
        "def run(arguments):\n    return {'text': arguments['text']}\n",
        encoding="utf-8",
    )
    (tool_dir / "requirements.lock").write_text("", encoding="utf-8")
    return tool_dir


def test_state_store_rejects_skipping_approval(tmp_path):
    store = ToolStateStore(tmp_path / "tool-state.json")
    store.register_draft("local.echo", "1.0.0", {"handler.py": "abc"})

    with pytest.raises(InvalidToolTransition):
        store.transition("local.echo", "1.0.0", "installed")


def test_state_store_marks_hash_change_broken(tmp_path):
    store = ToolStateStore(tmp_path / "tool-state.json")
    store.register_draft("local.echo", "1.0.0", {"handler.py": "abc"})
    for state in ("validating", "validated", "approved", "installed", "enabled"):
        store.transition("local.echo", "1.0.0", state)

    record = store.verify_integrity(
        "local.echo",
        "1.0.0",
        {"handler.py": "changed"},
    )

    assert record.state == "broken"


def test_catalog_exposes_only_enabled_tools(tmp_path):
    tools_root = tmp_path / "tools"
    enabled_dir = create_installed_tool(tools_root, "local.echo")
    create_installed_tool(tools_root, "local.disabled")
    store = ToolStateStore(tmp_path / "tool-state.json")
    for name, tool_dir in (
        ("local.echo", enabled_dir),
        ("local.disabled", tools_root / "local.disabled" / "1.0.0"),
    ):
        store.register_draft(name, "1.0.0", hash_tool_files(tool_dir))
        for state in ("validating", "validated", "approved", "installed"):
            store.transition(name, "1.0.0", state)
    store.transition("local.echo", "1.0.0", "enabled")

    catalog = ToolCatalog(tools_root, store)

    assert [tool.manifest.name for tool in catalog.list_enabled()] == ["local.echo"]


def test_state_file_is_valid_json(tmp_path):
    store = ToolStateStore(tmp_path / "tool-state.json")
    store.register_draft("local.echo", "1.0.0", {"handler.py": "abc"})

    payload = json.loads((tmp_path / "tool-state.json").read_text(encoding="utf-8"))

    assert payload["local.echo@1.0.0"]["state"] == "draft"
