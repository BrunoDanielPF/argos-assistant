import json

from assistant.capabilities.provisioning import CapabilityProvisioningService
from assistant.tools.audit import ToolAuditLog
from assistant.tools.generator import ToolDraftGenerator
from assistant.tools.state import ToolStateStore


def build_service(tmp_path):
    return CapabilityProvisioningService(
        generator=ToolDraftGenerator(
            tmp_path / "drafts",
            ToolStateStore(tmp_path / "tool-state.json"),
        ),
        audit_log=ToolAuditLog(tmp_path / "tools-audit.jsonl"),
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
