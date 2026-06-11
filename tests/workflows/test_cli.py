import json

import yaml
from typer.testing import CliRunner

from assistant.cli import app
from assistant.workflows.models import (
    PolicyDecision,
    Workflow,
    WorkflowBudget,
    WorkflowPolicy,
    WorkflowRunStatus,
    WorkflowStatus,
    WorkflowStep,
    WorkflowTrigger,
    WorkflowTriggerType,
)
from assistant.workflows.repository import WorkflowRepository


runner = CliRunner()


def generated_workflow(database):
    repository = WorkflowRepository(database)
    workflows = repository.list_workflows()
    repository.close()
    assert len(workflows) == 1
    return workflows[0]


def invoke_with_database(monkeypatch, database, arguments, input=None):
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))
    return runner.invoke(app, arguments, input=input)


def test_cli_workflows_generate_and_list(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"

    generated = invoke_with_database(
        monkeypatch,
        database,
        [
            "workflows",
            "generate",
            "todo dia às 9h, revise minhas tarefas",
        ],
    )
    listed = invoke_with_database(
        monkeypatch,
        database,
        ["workflows", "list"],
    )
    workflow = generated_workflow(database)

    assert generated.exit_code == 0
    assert "draft" in generated.stdout
    assert workflow.id[:8] in generated.stdout
    assert listed.exit_code == 0
    assert workflow.id[:8] in listed.stdout
    assert "Revisão diária de tarefas" in listed.stdout


def test_cli_workflows_inspect_and_export(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    invoke_with_database(
        monkeypatch,
        database,
        [
            "workflows",
            "generate",
            "quando um job falhar, me avise",
        ],
    )
    workflow = generated_workflow(database)

    inspected = invoke_with_database(
        monkeypatch,
        database,
        ["workflows", "inspect", workflow.id[:8]],
    )
    exported = invoke_with_database(
        monkeypatch,
        database,
        ["workflows", "export", workflow.id[:8]],
    )

    assert inspected.exit_code == 0
    assert json.loads(inspected.stdout)["id"] == workflow.id
    assert exported.exit_code == 0
    payload = yaml.safe_load(exported.stdout)
    assert payload["id"] == workflow.id
    assert payload["trigger"]["type"] == "job_failed"


def test_cli_workflows_validate_approve_enable_disable(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    invoke_with_database(
        monkeypatch,
        database,
        [
            "workflows",
            "generate",
            "todo dia às 9h, revise minhas tarefas",
        ],
    )
    workflow = generated_workflow(database)

    for command, expected_status in (
        ("validate", WorkflowStatus.VALIDATED),
        ("approve", WorkflowStatus.APPROVED),
        ("enable", WorkflowStatus.ENABLED),
        ("disable", WorkflowStatus.DISABLED),
    ):
        result = invoke_with_database(
            monkeypatch,
            database,
            ["workflows", command, workflow.id[:8]],
        )
        assert result.exit_code == 0
        assert expected_status.value in result.stdout
        repository = WorkflowRepository(database)
        assert repository.get_workflow(workflow.id).status == expected_status
        repository.close()


def test_cli_workflows_reject(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    invoke_with_database(
        monkeypatch,
        database,
        [
            "workflows",
            "generate",
            "quando um job falhar, me avise",
        ],
    )
    workflow = generated_workflow(database)

    result = invoke_with_database(
        monkeypatch,
        database,
        ["workflows", "reject", workflow.id],
    )

    assert result.exit_code == 0
    repository = WorkflowRepository(database)
    assert repository.get_workflow(workflow.id).status == WorkflowStatus.REJECTED
    repository.close()


def test_cli_workflows_run_and_logs(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    notifications = []
    monkeypatch.setattr(
        "assistant.cli.build_local_workflow_handlers",
        lambda notification_sink=None: {
            "notification.send": (
                lambda arguments: notifications.append(arguments) or {}
            )
        },
    )
    invoke_with_database(
        monkeypatch,
        database,
        [
            "workflows",
            "generate",
            "todo dia às 9h, revise minhas tarefas",
        ],
    )
    workflow = generated_workflow(database)
    for command in ("validate", "approve", "enable"):
        invoke_with_database(
            monkeypatch,
            database,
            ["workflows", command, workflow.id],
        )

    run = invoke_with_database(
        monkeypatch,
        database,
        ["workflows", "run", workflow.id],
    )
    logs = invoke_with_database(
        monkeypatch,
        database,
        ["workflows", "logs", workflow.id],
    )

    assert run.exit_code == 0
    assert WorkflowRunStatus.SUCCEEDED.value in run.stdout
    assert len(notifications) == 1
    assert logs.exit_code == 0
    assert "notification.send" not in logs.stdout
    assert "notify_task_review" in logs.stdout
    assert WorkflowRunStatus.SUCCEEDED.value in logs.stdout


def test_cli_workflows_run_waits_for_approval_non_interactively(
    monkeypatch,
    tmp_path,
):
    database = tmp_path / "argos.db"
    repository = WorkflowRepository(database)
    workflow = Workflow(
        name="Move with approval",
        status=WorkflowStatus.ENABLED,
        trigger=WorkflowTrigger(type=WorkflowTriggerType.MANUAL),
        steps=[
            WorkflowStep(
                id="move",
                name="Move",
                uses="files.move",
                with_args={"source": "a", "destination": "b"},
                requires_confirmation=True,
            )
        ],
        policy=WorkflowPolicy(
            actions={"files.move": PolicyDecision.CONFIRM}
        ),
        budget=WorkflowBudget(
            max_steps=1,
            max_runtime_seconds=30,
            max_model_calls=0,
            max_parallel_tasks=1,
        ),
    )
    repository.create_workflow(workflow)
    repository.close()

    result = invoke_with_database(
        monkeypatch,
        database,
        ["workflows", "run", workflow.id],
    )

    assert result.exit_code == 0
    assert WorkflowRunStatus.WAITING_APPROVAL.value in result.stdout


def test_cli_workflows_delete_archives_without_deleting(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    invoke_with_database(
        monkeypatch,
        database,
        [
            "workflows",
            "generate",
            "quando eu criar um .md, sugira organização",
        ],
    )
    workflow = generated_workflow(database)

    result = invoke_with_database(
        monkeypatch,
        database,
        ["workflows", "delete", workflow.id],
    )

    assert result.exit_code == 0
    repository = WorkflowRepository(database)
    archived = repository.get_workflow(workflow.id)
    repository.close()
    assert archived is not None
    assert archived.status == WorkflowStatus.ARCHIVED


def test_cli_workflows_rejects_invalid_transition(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    invoke_with_database(
        monkeypatch,
        database,
        [
            "workflows",
            "generate",
            "todo dia às 9h, revise minhas tarefas",
        ],
    )
    workflow = generated_workflow(database)

    result = invoke_with_database(
        monkeypatch,
        database,
        ["workflows", "enable", workflow.id],
    )

    assert result.exit_code == 1
    assert "Invalid workflow transition" in result.stdout


def test_cli_workflows_reports_missing_workflow(monkeypatch, tmp_path):
    result = invoke_with_database(
        monkeypatch,
        tmp_path / "argos.db",
        ["workflows", "inspect", "missing"],
    )

    assert result.exit_code == 1
    assert "Workflow nao encontrado" in result.stdout
