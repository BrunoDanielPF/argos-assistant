import pytest

from assistant.workflows.engine import (
    WorkflowEngine,
    WorkflowNotRunnable,
)
from assistant.workflows.models import (
    InvalidWorkflowTransition,
    WorkflowRunStatus,
    WorkflowStatus,
)
from assistant.workflows.planner import AdaptativeDynamicWorkflowPlanner
from assistant.workflows.repository import WorkflowRepository
from assistant.workflows.runner import SequentialWorkflowRunner
from assistant.workflows.validator import WorkflowValidator


def build_engine(tmp_path, handlers=None, confirmer=None):
    repository = WorkflowRepository(tmp_path / "argos.db")
    runner = SequentialWorkflowRunner(
        repository=repository,
        handlers=handlers or {"notification.send": lambda arguments: {}},
        confirmer=confirmer,
    )
    return (
        WorkflowEngine(
            repository=repository,
            planner=AdaptativeDynamicWorkflowPlanner(),
            validator=WorkflowValidator(),
            runner=runner,
        ),
        repository,
    )


def test_engine_generates_and_persists_draft(tmp_path):
    engine, repository = build_engine(tmp_path)

    workflow = engine.generate("todo dia às 9h, revise minhas tarefas")

    assert workflow.status == WorkflowStatus.DRAFT
    assert repository.get_workflow(workflow.id) == workflow
    repository.close()


def test_engine_validates_approves_and_enables_in_order(tmp_path):
    engine, repository = build_engine(tmp_path)
    workflow = engine.generate("todo dia às 9h, revise minhas tarefas")

    validated = engine.validate(workflow.id)
    approved = engine.approve(workflow.id)
    enabled = engine.enable(workflow.id)

    assert validated.status == WorkflowStatus.VALIDATED
    assert approved.status == WorkflowStatus.APPROVED
    assert enabled.status == WorkflowStatus.ENABLED
    repository.close()


def test_engine_rejects_invalid_lifecycle_order(tmp_path):
    engine, repository = build_engine(tmp_path)
    workflow = engine.generate("todo dia às 9h, revise minhas tarefas")

    with pytest.raises(InvalidWorkflowTransition):
        engine.approve(workflow.id)

    repository.close()


def test_engine_rejects_and_archives_without_physical_delete(tmp_path):
    engine, repository = build_engine(tmp_path)
    rejected = engine.generate("todo dia às 9h, revise minhas tarefas")
    archived = engine.generate("quando um job falhar, me avise")

    rejected = engine.reject(rejected.id)
    archived = engine.archive(archived.id)

    assert rejected.status == WorkflowStatus.REJECTED
    assert archived.status == WorkflowStatus.ARCHIVED
    assert repository.get_workflow(archived.id) is not None
    repository.close()


def test_engine_disables_enabled_workflow(tmp_path):
    engine, repository = build_engine(tmp_path)
    workflow = engine.generate("todo dia às 9h, revise minhas tarefas")
    engine.validate(workflow.id)
    engine.approve(workflow.id)
    engine.enable(workflow.id)

    disabled = engine.disable(workflow.id)

    assert disabled.status == WorkflowStatus.DISABLED
    repository.close()


def test_engine_runs_only_enabled_workflows(tmp_path):
    calls = []
    engine, repository = build_engine(
        tmp_path,
        handlers={
            "notification.send": lambda arguments: calls.append(arguments) or {}
        },
    )
    workflow = engine.generate("todo dia às 9h, revise minhas tarefas")

    with pytest.raises(WorkflowNotRunnable):
        engine.run(workflow.id)

    engine.validate(workflow.id)
    engine.approve(workflow.id)
    engine.enable(workflow.id)
    run = engine.run(workflow.id, trigger_event={"source": "manual"})

    assert run.status == WorkflowRunStatus.SUCCEEDED
    assert len(calls) == 1
    repository.close()


def test_engine_resolves_unique_workflow_prefix(tmp_path):
    engine, repository = build_engine(tmp_path)
    workflow = engine.generate("todo dia às 9h, revise minhas tarefas")

    loaded = engine.get(workflow.id[:8])

    assert loaded.id == workflow.id
    repository.close()
