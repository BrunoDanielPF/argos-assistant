import json

import pytest

from assistant.tools.generator import InvalidToolName, ToolDraftGenerator
from assistant.tools.installer import ToolApprovalRequired, ToolInstaller
from assistant.tools.state import ToolStateStore, hash_tool_files

from tests.tools.test_state_catalog import create_installed_tool


def test_generator_creates_inactive_validated_draft(tmp_path):
    state = ToolStateStore(tmp_path / "tool-state.json")
    generator = ToolDraftGenerator(tmp_path / "drafts", state)

    draft = generator.generate(
        {
            "name": "local.generated.echo",
            "version": "1.0.0",
            "title": "Generated Echo",
            "description": "Retorna o texto.",
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
            },
            "output_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
            },
            "handler_body": "def run(arguments):\n    return {}\n",
        }
    )

    assert draft.state == "validated"
    assert draft.can_execute is False
    assert (draft.path / "validation-report.json").exists()


def test_generator_reuses_equivalent_validated_draft(tmp_path):
    state = ToolStateStore(tmp_path / "tool-state.json")
    generator = ToolDraftGenerator(tmp_path / "drafts", state)
    definition = {
        "name": "local.generated.echo",
        "version": "1.0.0",
        "handler_body": "def run(arguments):\n    return arguments\n",
    }

    first = generator.generate(definition)
    second = generator.generate(definition)

    assert second == first
    assert state.get("local.generated.echo", "1.0.0").state == "validated"


def test_generator_rejects_same_version_with_different_definition(tmp_path):
    state = ToolStateStore(tmp_path / "tool-state.json")
    generator = ToolDraftGenerator(tmp_path / "drafts", state)
    generator.generate(
        {
            "name": "local.generated.echo",
            "version": "1.0.0",
            "handler_body": "def run(arguments):\n    return arguments\n",
        }
    )

    with pytest.raises(FileExistsError):
        generator.generate(
            {
                "name": "local.generated.echo",
                "version": "1.0.0",
                "handler_body": (
                    "def run(arguments):\n"
                    "    return {'changed': True}\n"
                ),
            }
        )


def test_generator_rejects_invalid_name(tmp_path):
    generator = ToolDraftGenerator(
        tmp_path / "drafts",
        ToolStateStore(tmp_path / "state.json"),
    )

    with pytest.raises(InvalidToolName):
        generator.generate({"name": "../../evil"})


def test_installer_requires_approved_state(tmp_path):
    source = create_installed_tool(tmp_path / "drafts")
    store = ToolStateStore(tmp_path / "state.json")
    store.register_draft("local.echo", "1.0.0", hash_tool_files(source))
    installer = ToolInstaller(
        tools_root=tmp_path / "tools",
        envs_root=tmp_path / "envs",
        state_store=store,
    )

    with pytest.raises(ToolApprovalRequired):
        installer.install(source)


def test_installer_copies_approved_tool_without_pip_for_empty_lock(tmp_path):
    source = create_installed_tool(tmp_path / "drafts")
    store = ToolStateStore(tmp_path / "state.json")
    store.register_draft("local.echo", "1.0.0", hash_tool_files(source))
    for state in ("validating", "validated", "approved"):
        store.transition("local.echo", "1.0.0", state)
    commands = []
    installer = ToolInstaller(
        tools_root=tmp_path / "tools",
        envs_root=tmp_path / "envs",
        state_store=store,
        create_environment=False,
        command_runner=lambda command: commands.append(command),
    )

    installed = installer.install(source)

    assert installed == tmp_path / "tools" / "local.echo" / "1.0.0"
    assert commands == []
    assert store.get("local.echo", "1.0.0").state == "installed"
    assert json.loads((tmp_path / "state.json").read_text())["local.echo@1.0.0"]
