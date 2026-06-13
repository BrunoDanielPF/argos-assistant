from datetime import datetime, timedelta, timezone
import sqlite3

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from assistant.capabilities.adaptive_capability_graph import (
    AdaptiveCapabilityGraph,
)
from assistant.capabilities.definitions import ToolDefinition
from assistant.capabilities.provisioning import CapabilityProvisioningService
from assistant.capabilities.templates import ToolDefinitionSource
from assistant.capabilities.workflow_repository import (
    CapabilityWorkflowRepository,
)
from assistant.tools.generator import ToolDraftGenerator
from assistant.tools.installer import ToolInstaller
from assistant.tools.state import ToolStateStore

from tests.capabilities.test_model_definition_source import metadata_definition


class MetadataSource(ToolDefinitionSource):
    source_kind = "model"

    def build_candidate(self, **_kwargs):
        return ToolDefinition.model_validate(metadata_definition())


def build_graph(tmp_path, *, execute_action=None, audit=None):
    state_store = ToolStateStore(tmp_path / "tool-state.json")
    provisioning = CapabilityProvisioningService(
        generator=ToolDraftGenerator(tmp_path / "tool-drafts", state_store),
        state_store=state_store,
        installer=ToolInstaller(
            tools_root=tmp_path / "tools",
            envs_root=tmp_path / "envs",
            state_store=state_store,
            create_environment=False,
        ),
        definition_sources=[MetadataSource()],
    )
    repository = CapabilityWorkflowRepository(
        tmp_path / "workflows.db",
        now_fn=lambda: datetime(2026, 6, 13, tzinfo=timezone.utc),
    )
    reloads = []
    graph = AdaptiveCapabilityGraph(
        provisioning_service=provisioning,
        repository=repository,
        checkpointer=InMemorySaver(),
        reload_session=lambda session_id: reloads.append(session_id),
        execute_action=execute_action or (lambda _session_id, action: {"ok": True, "action": action}),
        policy_decider=lambda _capability, _arguments, _context: "allow",
        audit=audit,
        ttl=timedelta(hours=24),
    )
    return graph, repository, reloads


def start_metadata_workflow(graph):
    return graph.start(
        session_id="session-1",
        run_id="run-1",
        requested_capability="file.metadata.stat",
        user_goal="quero a data de criacao do arquivo notes.txt",
        arguments={"path": "notes.txt"},
        platform_context={"platform": "win32", "current_cwd": "C:/work"},
        original_action={
            "mode": "action",
            "capability": "file.metadata.stat",
            "arguments": {"path": "notes.txt"},
        },
    )


def test_start_auto_creates_validated_draft_and_pauses_for_approval(tmp_path):
    graph, repository, _reloads = build_graph(tmp_path)

    result = start_metadata_workflow(graph)

    assert result["ok"] is True
    assert result["result"] == "pending_approval"
    assert result["status"] == "WAITING_TOOL_APPROVAL"
    assert result["error_code"] is None
    assert result["approval"]["options"] == [
        "approve_enable_and_run_once",
        "approve_enable_only",
        "reject",
        "cancel",
    ]
    record = repository.load(result["workflow_id"])
    assert record is not None
    assert record.status == "WAITING_TOOL_APPROVAL"
    assert record.draft_path.endswith("file.metadata.stat\\1.0.0")


def test_approve_enable_only_reloads_session_and_requires_retry_confirmation(tmp_path):
    graph, repository, reloads = build_graph(tmp_path)
    pending = start_metadata_workflow(graph)

    resumed = graph.decide_tool(
        pending["workflow_id"],
        "approve_enable_only",
    )

    assert resumed["result"] == "pending_confirmation"
    assert resumed["status"] == "WAITING_RETRY_CONFIRMATION"
    assert resumed["approval"]["dry_run"]["risk"] == "low"
    assert reloads == ["session-1"]
    assert repository.load(pending["workflow_id"]).status == (
        "WAITING_RETRY_CONFIRMATION"
    )


def test_reject_is_terminal_and_does_not_enable(tmp_path):
    graph, repository, reloads = build_graph(tmp_path)
    pending = start_metadata_workflow(graph)

    result = graph.decide_tool(pending["workflow_id"], "reject")

    assert result["status"] == "TOOL_REJECTED"
    assert result["result"] == "rejected"
    assert reloads == []
    assert repository.load(pending["workflow_id"]).status == "TOOL_REJECTED"


def test_enable_and_run_once_executes_once_and_duplicate_decision_is_idempotent(
    tmp_path,
):
    executions = []
    graph, repository, reloads = build_graph(
        tmp_path,
        execute_action=lambda session_id, action: executions.append(
            (session_id, action)
        )
        or {"ok": True},
    )
    pending = start_metadata_workflow(graph)

    first = graph.decide_tool(
        pending["workflow_id"],
        "approve_enable_and_run_once",
    )
    second = graph.decide_tool(
        pending["workflow_id"],
        "approve_enable_and_run_once",
    )

    assert first["status"] == "ACTION_EXECUTED"
    assert second["status"] == "ACTION_EXECUTED"
    assert reloads == ["session-1"]
    assert len(executions) == 1
    assert repository.load(pending["workflow_id"]).retry_status == "executed"


def test_run_once_ineligible_is_downgraded_and_audited(tmp_path):
    events = []
    graph, _repository, _reloads = build_graph(
        tmp_path,
        audit=lambda event, details: events.append((event, details)),
    )
    pending = start_metadata_workflow(graph)
    graph._policy_decider = lambda *_args: "confirm"

    result = graph.decide_tool(
        pending["workflow_id"],
        "approve_enable_and_run_once",
    )

    assert result["status"] == "WAITING_RETRY_CONFIRMATION"
    assert any(event == "run_once_downgraded" for event, _ in events)


def test_list_and_cancel_pending_workflow(tmp_path):
    graph, _repository, _reloads = build_graph(tmp_path)
    pending = start_metadata_workflow(graph)

    listed = graph.list_pending("session-1")
    cancelled = graph.cancel(pending["workflow_id"])

    assert [item["workflow_id"] for item in listed] == [
        pending["workflow_id"]
    ]
    assert cancelled["status"] == "TOOL_APPROVAL_CANCELLED"
    assert graph.list_pending("session-1") == []


def test_cleanup_expires_workflow_and_removes_quarantined_draft(tmp_path):
    graph, repository, _reloads = build_graph(tmp_path)
    pending = start_metadata_workflow(graph)
    draft_path = repository.load(pending["workflow_id"]).draft_path

    expired = graph.cleanup_expired(
        now=datetime(2030, 1, 1, tzinfo=timezone.utc)
    )

    assert expired == [pending["workflow_id"]]
    assert repository.load(pending["workflow_id"]).status == "WORKFLOW_EXPIRED"
    assert not __import__("pathlib").Path(draft_path).exists()


def test_sqlite_checkpointer_resumes_after_graph_recreation(tmp_path):
    checkpoint_file = tmp_path / "checkpoints.db"
    connection = sqlite3.connect(checkpoint_file, check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    first, first_repository, _reloads = build_graph(tmp_path)
    first._graph = first._build_graph().compile(checkpointer=saver)
    pending = start_metadata_workflow(first)
    first_repository.close()
    connection.close()

    second_connection = sqlite3.connect(
        checkpoint_file,
        check_same_thread=False,
    )
    second_saver = SqliteSaver(second_connection)
    second_saver.setup()
    state_store = ToolStateStore(tmp_path / "tool-state.json")
    provisioning = CapabilityProvisioningService(
        generator=ToolDraftGenerator(tmp_path / "tool-drafts", state_store),
        state_store=state_store,
        installer=ToolInstaller(
            tools_root=tmp_path / "tools",
            envs_root=tmp_path / "envs",
            state_store=state_store,
            create_environment=False,
        ),
        definition_sources=[MetadataSource()],
    )
    second_repository = CapabilityWorkflowRepository(
        tmp_path / "workflows.db"
    )
    resumed_graph = AdaptiveCapabilityGraph(
        provisioning_service=provisioning,
        repository=second_repository,
        checkpointer=second_saver,
        reload_session=lambda _session_id: None,
        execute_action=lambda _session_id, _action: {"ok": True},
        policy_decider=lambda *_args: "allow",
    )

    resumed = resumed_graph.decide_tool(
        pending["workflow_id"],
        "approve_enable_only",
    )

    assert resumed["status"] == "WAITING_RETRY_CONFIRMATION"
    second_repository.close()
    second_connection.close()


def test_sensitive_environment_value_is_not_persisted_in_workflow_state(
    tmp_path,
):
    checkpoint_file = tmp_path / "checkpoints.db"
    connection = sqlite3.connect(checkpoint_file, check_same_thread=False)
    saver = SqliteSaver(connection)
    saver.setup()
    state_store = ToolStateStore(tmp_path / "tool-state.json")
    provisioning = CapabilityProvisioningService(
        generator=ToolDraftGenerator(tmp_path / "tool-drafts", state_store),
        state_store=state_store,
        installer=ToolInstaller(
            tools_root=tmp_path / "tools",
            envs_root=tmp_path / "envs",
            state_store=state_store,
            create_environment=False,
        ),
    )
    repository = CapabilityWorkflowRepository(tmp_path / "workflows.db")
    graph = AdaptiveCapabilityGraph(
        provisioning_service=provisioning,
        repository=repository,
        checkpointer=saver,
        reload_session=lambda _session_id: None,
        execute_action=lambda _session_id, _action: {"ok": True},
        policy_decider=lambda *_args: "confirm",
    )

    pending = graph.start(
        session_id="s1",
        run_id="r1",
        requested_capability="windows.env.set_user",
        user_goal="configure ARGOS_TESTE com valor 456",
        arguments={"name": "ARGOS_TESTE", "value": "456"},
        platform_context={"platform": "win32"},
        original_action={
            "mode": "action",
            "capability": "windows.env.set_user",
            "arguments": {"name": "ARGOS_TESTE", "value": "456"},
        },
    )
    record = repository.load(pending["workflow_id"])

    assert "456" not in record.model_dump_json()
    connection.commit()
    assert b"456" not in checkpoint_file.read_bytes()
    repository.close()
    connection.close()
