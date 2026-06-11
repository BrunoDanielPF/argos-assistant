import json

import pytest
from typer.testing import CliRunner

from assistant.cli import app
from assistant.workflows.engine import WorkflowEngine
from assistant.workflows.models import (
    InvalidWorkflowTransition,
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
from assistant.workflows.planner import AdaptativeDynamicWorkflowPlanner
from assistant.workflows.repository import WorkflowRepository
from assistant.workflows.runner import SequentialWorkflowRunner
from assistant.workflows.validator import WorkflowValidator


PDF_PROMPT = "quando eu baixar um PDF, sugira mover para a pasta correta"


def pdf_workflow():
    return AdaptativeDynamicWorkflowPlanner().generate(PDF_PROMPT)


def validation_codes(payload):
    return {
        finding.code
        for finding in WorkflowValidator().validate(payload).findings
    }


def build_engine(tmp_path, handlers=None):
    repository = WorkflowRepository(tmp_path / "argos.db")
    engine = WorkflowEngine(
        repository=repository,
        planner=AdaptativeDynamicWorkflowPlanner(),
        validator=WorkflowValidator(),
        runner=SequentialWorkflowRunner(
            repository=repository,
            handlers=handlers or {"noop": lambda arguments: arguments},
        ),
    )
    return engine, repository


def noop_workflow(status=WorkflowStatus.ENABLED, with_args=None):
    return Workflow(
        name="Noop acceptance",
        status=status,
        trigger=WorkflowTrigger(type=WorkflowTriggerType.MANUAL),
        steps=[
            WorkflowStep(
                id="noop",
                name="Noop",
                uses="noop",
                with_args=with_args or {},
            )
        ],
        policy=WorkflowPolicy(
            actions={"noop": PolicyDecision.ALLOW}
        ),
        budget=WorkflowBudget(
            max_steps=1,
            max_runtime_seconds=30,
            max_model_calls=0,
            max_parallel_tasks=1,
        ),
    )


def test_01_pdf_workflow_is_created_as_draft():
    assert pdf_workflow().status == WorkflowStatus.DRAFT


def test_02_pdf_workflow_uses_file_created_trigger():
    assert pdf_workflow().trigger.type == WorkflowTriggerType.FILE_CREATED


def test_03_pdf_workflow_uses_pdf_pattern():
    assert pdf_workflow().trigger.arguments["pattern"] == "*.pdf"


def test_04_pdf_workflow_contains_files_move():
    assert "files.move" in {step.uses for step in pdf_workflow().steps}


def test_05_files_move_requires_confirmation():
    workflow = pdf_workflow()
    move = next(step for step in workflow.steps if step.uses == "files.move")

    assert move.requires_confirmation is True
    assert workflow.policy.actions["files.move"] == PolicyDecision.CONFIRM


def test_06_generated_workflow_never_starts_enabled():
    assert pdf_workflow().status != WorkflowStatus.ENABLED


def test_07_workflow_without_budget_fails_validation():
    payload = pdf_workflow().model_dump(mode="json")
    payload.pop("budget")

    assert "budget_required" in validation_codes(payload)


def test_08_unknown_step_fails_validation():
    payload = pdf_workflow().model_dump(mode="json")
    payload["steps"][0]["uses"] = "python.eval"

    assert "handler_unknown" in validation_codes(payload)


def test_09_destructive_shell_fails_validation():
    payload = pdf_workflow().model_dump(mode="json")
    payload["steps"] = [
        {
            "id": "shell",
            "name": "Shell",
            "uses": "shell.run",
            "with_args": {"command": "rm -rf ./data"},
            "requires_confirmation": True,
            "timeout_seconds": 60,
            "continue_on_error": False,
            "if_condition": None,
        }
    ]
    payload["policy"]["actions"] = {"shell.run": "confirm"}

    assert "shell_command_destructive" in validation_codes(payload)


def test_10_approve_changes_status_to_approved(tmp_path):
    engine, repository = build_engine(tmp_path)
    workflow = engine.generate(PDF_PROMPT)
    engine.validate(workflow.id)

    approved = engine.approve(workflow.id)

    assert approved.status == WorkflowStatus.APPROVED
    repository.close()


def test_11_enable_only_works_after_approved(tmp_path):
    engine, repository = build_engine(tmp_path)
    workflow = engine.generate(PDF_PROMPT)

    with pytest.raises(InvalidWorkflowTransition):
        engine.enable(workflow.id)

    engine.validate(workflow.id)
    engine.approve(workflow.id)
    assert engine.enable(workflow.id).status == WorkflowStatus.ENABLED
    repository.close()


def test_12_rejected_workflow_cannot_be_enabled(tmp_path):
    engine, repository = build_engine(tmp_path)
    workflow = engine.generate(PDF_PROMPT)
    engine.reject(workflow.id)

    with pytest.raises(InvalidWorkflowTransition):
        engine.enable(workflow.id)

    repository.close()


def test_13_sequential_runner_executes_noop(tmp_path):
    calls = []
    workflow = noop_workflow(with_args={"value": 1})
    repository = WorkflowRepository(tmp_path / "argos.db")
    repository.create_workflow(workflow)

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"noop": lambda arguments: calls.append(arguments) or arguments},
    ).run(workflow)

    assert run.status == WorkflowRunStatus.SUCCEEDED
    assert calls == [{"value": 1}]
    repository.close()


def test_14_runner_respects_max_steps(tmp_path):
    calls = []
    workflow = noop_workflow()
    workflow.steps.append(
        WorkflowStep(id="second", name="Second", uses="noop")
    )
    repository = WorkflowRepository(tmp_path / "argos.db")
    repository.create_workflow(workflow)

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"noop": lambda arguments: calls.append(arguments)},
    ).run(workflow)

    assert run.status == WorkflowRunStatus.BLOCKED
    assert calls == []
    repository.close()


def test_15_run_creates_persisted_workflow_run(tmp_path):
    workflow = noop_workflow()
    repository = WorkflowRepository(tmp_path / "argos.db")
    repository.create_workflow(workflow)

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"noop": lambda arguments: {}},
    ).run(workflow)

    assert repository.get_run(run.id) == run
    assert repository.list_runs(workflow.id) == [run]
    repository.close()


def test_16_logs_redact_sensitive_values(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    secrets = {
        "secret": "secret-value",
        "token": "token-value",
        "password": "password-value",
        "api_key": "api-key-value",
        "private_key": "private-key-value",
        "nested": {"API-Key": "nested-api-key-value"},
        "tokens": ["plural-token-value"],
        "passwords": {"service": "plural-password-value"},
        "secrets": "plural-secret-value",
    }
    workflow = noop_workflow(with_args=secrets)
    repository = WorkflowRepository(database)
    repository.create_workflow(workflow)
    SequentialWorkflowRunner(
        repository=repository,
        handlers={"noop": lambda arguments: arguments},
    ).run(workflow, trigger_event={"token": "trigger-token-value"})
    repository.close()
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))

    result = CliRunner().invoke(
        app,
        ["workflows", "logs", workflow.id],
    )

    assert result.exit_code == 0
    assert result.stdout.count("[REDACTED]") >= 6
    for value in (
        "secret-value",
        "token-value",
        "password-value",
        "api-key-value",
        "private-key-value",
        "nested-api-key-value",
        "trigger-token-value",
        "plural-token-value",
        "plural-password-value",
        "plural-secret-value",
    ):
        assert value not in result.stdout


def test_17_cli_workflows_generate_works(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))

    result = CliRunner().invoke(
        app,
        ["workflows", "generate", PDF_PROMPT],
    )

    assert result.exit_code == 0
    assert "draft" in result.stdout


def test_18_cli_workflows_inspect_works(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    repository = WorkflowRepository(database)
    workflow = repository.create_workflow(pdf_workflow())
    repository.close()
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))

    result = CliRunner().invoke(
        app,
        ["workflows", "inspect", workflow.id],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["id"] == workflow.id


def test_19_cli_workflows_run_executes_noop(monkeypatch, tmp_path):
    database = tmp_path / "argos.db"
    workflow = noop_workflow()
    repository = WorkflowRepository(database)
    repository.create_workflow(workflow)
    repository.close()
    calls = []
    monkeypatch.setenv("ARGOS_DATABASE_FILE", str(database))
    monkeypatch.setattr(
        "assistant.cli.build_local_workflow_handlers",
        lambda notification_sink=None: {
            "noop": lambda arguments: calls.append(arguments) or {}
        },
    )

    result = CliRunner().invoke(
        app,
        ["workflows", "run", workflow.id],
    )

    assert result.exit_code == 0
    assert WorkflowRunStatus.SUCCEEDED.value in result.stdout
    assert calls == [{}]
