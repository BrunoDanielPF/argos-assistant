import json
from copy import deepcopy

from assistant.capabilities.definitions import ToolDefinition
from assistant.capabilities.provisioning import CapabilityProvisioningService
from assistant.capabilities.templates import SafeToolTemplateCatalog
from assistant.tools.audit import ToolAuditLog
from assistant.tools.generator import ToolDraftGenerator
from assistant.tools.installer import ToolInstaller
from assistant.tools.state import ToolStateStore
from tests.capabilities.test_model_definition_source import (
    metadata_definition,
)


def build_service(tmp_path, *, definition_sources=None):
    state_store = ToolStateStore(tmp_path / "tool-state.json")
    return CapabilityProvisioningService(
        generator=ToolDraftGenerator(
            tmp_path / "drafts",
            state_store,
        ),
        state_store=state_store,
        installer=ToolInstaller(
            tools_root=tmp_path / "tools",
            envs_root=tmp_path / "envs",
            state_store=state_store,
            create_environment=False,
        ),
        audit_log=ToolAuditLog(tmp_path / "tools-audit.jsonl"),
        definition_sources=definition_sources,
    )


def test_shell_git_status_proposes_narrow_local_tool(tmp_path):
    service = build_service(tmp_path)

    proposal = service.propose(
        requested_capability="shell.run",
        user_goal="rode o comando git status",
        arguments={"command": "git status"},
        platform_context={
            "platform": "win32",
            "current_cwd": str(tmp_path),
        },
        original_action={
            "capability": "shell.run",
            "arguments": {"command": "git status"},
        },
    )

    assert proposal.can_create is True
    assert proposal.definition is not None
    definition = proposal.definition.model_dump()
    assert definition["name"] == "local.git.status"
    assert definition["permissions"]["network"] == {
        "enabled": False,
        "hosts": [],
    }
    assert definition["permissions"]["filesystem"]["write"] == []
    assert definition["permissions"]["subprocess"]["executables"] == ["git"]
    assert "shell=True" not in definition["handler_body"]
    assert "arguments['command']" not in definition["handler_body"]
    assert proposal.tool_definition_hash


def test_windows_user_environment_proposes_no_shell_or_network(tmp_path):
    service = build_service(tmp_path)

    proposal = service.propose(
        requested_capability="windows.env.set_user",
        user_goal="configure ARGOS_TESTE_NOVA com valor 456",
        arguments={"name": "ARGOS_TESTE_NOVA", "value": "456"},
        platform_context={"platform": "win32"},
        original_action={
            "capability": "windows.env.set_user",
            "arguments": {"name": "ARGOS_TESTE_NOVA", "value": "456"},
        },
    )

    assert proposal.can_create is True
    assert proposal.definition is not None
    definition = proposal.definition.model_dump()
    assert definition["name"] == "local.windows.env_set_user"
    assert definition["permissions"]["filesystem"] == {
        "read": [],
        "write": [],
    }
    assert definition["permissions"]["network"]["enabled"] is False
    assert definition["permissions"]["subprocess"]["executables"] == []
    assert "winreg" in definition["handler_body"]


def test_destructive_shell_action_is_not_eligible_for_draft(tmp_path):
    service = build_service(tmp_path)

    proposal = service.propose(
        requested_capability="shell.run",
        user_goal="apague tudo",
        arguments={"command": "rm -rf ."},
        platform_context={"platform": "linux"},
        original_action={
            "capability": "shell.run",
            "arguments": {"command": "rm -rf ."},
        },
    )

    assert proposal.can_create is False
    assert proposal.definition is None
    assert proposal.reason == "destructive_action"
    assert not (tmp_path / "drafts").exists()


def test_approved_proposal_creates_validated_inactive_draft_and_audits(tmp_path):
    service = build_service(tmp_path)
    proposal = service.propose(
        requested_capability="shell.run",
        user_goal="rode o comando git status",
        arguments={"command": "git status"},
        platform_context={
            "platform": "win32",
            "current_cwd": str(tmp_path),
        },
        original_action={
            "capability": "shell.run",
            "arguments": {"command": "git status"},
        },
    )

    draft = service.create_draft(proposal)

    assert draft.state == "validated"
    assert draft.can_execute is False
    assert draft.path == tmp_path / "drafts" / "local.git.status" / "1.0.0"
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "tools-audit.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert events == ["draft_proposed", "draft_created"]


def test_explicit_lifecycle_approval_installs_and_enables_tool(tmp_path):
    service = build_service(tmp_path)
    proposal = service.propose(
        requested_capability="windows.env.set_user",
        user_goal="configure TESTE com valor 456",
        arguments={"name": "TESTE", "value": "456"},
        platform_context={"platform": "win32"},
        original_action={
            "mode": "action",
            "capability": "windows.env.set_user",
            "arguments": {"name": "TESTE", "value": "456"},
        },
    )
    draft = service.create_draft(proposal)

    enabled = service.approve_install_enable(
        proposal=proposal,
        draft_path=draft.path,
    )

    assert enabled.state == "enabled"
    assert enabled.tool_name == "local.windows.env_set_user"
    assert enabled.installed_path == (
        tmp_path
        / "tools"
        / "local.windows.env_set_user"
        / "1.0.0"
    )
    assert enabled.original_action == proposal.original_action
    state = ToolStateStore(tmp_path / "tool-state.json")
    assert state.get("local.windows.env_set_user", "1.0.0").state == (
        "enabled"
    )
    events = [
        json.loads(line)["event"]
        for line in (tmp_path / "tools-audit.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert events[-3:] == [
        "tool_approved",
        "tool_installed",
        "tool_enabled",
    ]


def test_rejected_lifecycle_keeps_validated_draft(tmp_path):
    service = build_service(tmp_path)
    proposal = service.propose(
        requested_capability="windows.env.set_user",
        user_goal="configure TESTE com valor 456",
        arguments={"name": "TESTE", "value": "456"},
        platform_context={"platform": "win32"},
        original_action={},
    )
    service.create_draft(proposal)

    service.reject_enablement(proposal)

    state = ToolStateStore(tmp_path / "tool-state.json")
    assert state.get("local.windows.env_set_user", "1.0.0").state == (
        "validated"
    )
    assert not (tmp_path / "tools").exists()


def test_definition_hash_is_stable_for_equivalent_definitions(tmp_path):
    source_definition = SafeToolTemplateCatalog().build_candidate(
        requested_capability="windows.env.set_user",
        user_goal="configure TESTE",
        arguments={"name": "TESTE", "value": "456"},
        platform_context={"platform": "win32"},
        original_action={},
    )

    class StaticSource:
        def build_candidate(self, **kwargs):
            return ToolDefinition.model_validate(
                source_definition.model_dump()
            )

    first = build_service(
        tmp_path / "first",
        definition_sources=[StaticSource()],
    ).propose(
        requested_capability="custom.read",
        user_goal="read",
        arguments={},
        platform_context={},
        original_action={},
    )
    second = build_service(
        tmp_path / "second",
        definition_sources=[StaticSource()],
    ).propose(
        requested_capability="custom.read",
        user_goal="read",
        arguments={},
        platform_context={},
        original_action={},
    )

    assert first.tool_definition_hash == second.tool_definition_hash


def test_safe_template_precedes_model_source(tmp_path):
    class FailIfCalledSource:
        def build_candidate(self, **kwargs):
            raise AssertionError("model source must not run for safe template")

    service = build_service(
        tmp_path,
        definition_sources=[
            SafeToolTemplateCatalog(),
            FailIfCalledSource(),
        ],
    )

    proposal = service.propose(
        requested_capability="windows.env.set_user",
        user_goal="configure TESTE com valor 456",
        arguments={"name": "TESTE", "value": "456"},
        platform_context={"platform": "win32"},
        original_action={},
    )

    assert proposal.definition.name == "local.windows.env_set_user"


def test_model_backed_definition_must_pass_read_only_policy(tmp_path):
    unsafe = deepcopy(metadata_definition())
    unsafe["permissions"]["network"] = {
        "enabled": True,
        "hosts": ["example.com"],
    }

    class UnsafeModelSource:
        source_kind = "model"

        def build_candidate(self, **kwargs):
            return ToolDefinition.model_validate(unsafe)

    proposal = build_service(
        tmp_path,
        definition_sources=[
            SafeToolTemplateCatalog(),
            UnsafeModelSource(),
        ],
    ).propose(
        requested_capability="file.metadata.stat",
        user_goal="metadata",
        arguments={"path": "notes.txt"},
        platform_context={},
        original_action={},
    )

    assert proposal.status == "blocked"
    assert proposal.definition is None
    assert proposal.reason == "generated_tool_unsafe:network_not_allowed"


def test_safe_model_backed_definition_is_proposed(tmp_path):
    class SafeModelSource:
        source_kind = "model"

        def build_candidate(self, **kwargs):
            return ToolDefinition.model_validate(metadata_definition())

    proposal = build_service(
        tmp_path,
        definition_sources=[
            SafeToolTemplateCatalog(),
            SafeModelSource(),
        ],
    ).propose(
        requested_capability="file.metadata.stat",
        user_goal="metadata",
        arguments={"path": "notes.txt"},
        platform_context={},
        original_action={},
    )

    assert proposal.status == "proposed"
    assert proposal.definition.name == "file.metadata.stat"
