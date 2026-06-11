from datetime import timezone

import pytest

from assistant.workflows.models import (
    InvalidWorkflowTransition,
    PolicyDecision,
    Workflow,
    WorkflowBudget,
    WorkflowPolicy,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunStep,
    WorkflowRunStepStatus,
    WorkflowStatus,
    WorkflowStep,
    WorkflowTrigger,
    WorkflowTriggerType,
)
from assistant.workflows.repository import WorkflowRepository


def build_workflow(name: str = "Organizar PDFs") -> Workflow:
    return Workflow(
        name=name,
        description="Organiza novos PDFs com confirmação.",
        trigger=WorkflowTrigger(
            type=WorkflowTriggerType.FILE_CREATED,
            arguments={"path": "~/Downloads", "pattern": "*.pdf"},
        ),
        steps=[
            WorkflowStep(
                id="inspect",
                name="Inspecionar",
                uses="files.inspect",
                with_args={"path": "${trigger.path}"},
            ),
            WorkflowStep(
                id="move",
                name="Mover",
                uses="files.move",
                with_args={"source": "${trigger.path}"},
                requires_confirmation=True,
            ),
        ],
        policy=WorkflowPolicy(
            actions={
                "files.inspect": PolicyDecision.ALLOW,
                "files.move": PolicyDecision.CONFIRM,
            }
        ),
        budget=WorkflowBudget(
            max_steps=4,
            max_runtime_seconds=120,
            max_model_calls=1,
            max_parallel_tasks=1,
        ),
        scope={"root": "~/Downloads"},
        source_prompt="quando eu baixar um PDF, sugira mover",
        metadata={"planner": "heuristic"},
    )


def test_repository_saves_and_loads_workflow_losslessly(tmp_path):
    repository = WorkflowRepository(tmp_path / "argos.db")
    workflow = build_workflow()

    saved = repository.create_workflow(workflow)
    loaded = repository.get_workflow(workflow.id)

    assert saved == workflow
    assert loaded == workflow
    assert loaded.trigger.arguments["pattern"] == "*.pdf"
    assert loaded.steps[1].requires_confirmation is True
    assert loaded.policy.actions["files.move"] == PolicyDecision.CONFIRM
    assert loaded.scope == {"root": "~/Downloads"}
    assert loaded.metadata == {"planner": "heuristic"}
    repository.close()


def test_repository_persists_workflow_after_reopen(tmp_path):
    database = tmp_path / "argos.db"
    first = WorkflowRepository(database)
    workflow = first.create_workflow(build_workflow())
    first.close()

    second = WorkflowRepository(database)
    loaded = second.get_workflow(workflow.id)

    assert loaded is not None
    assert loaded.name == "Organizar PDFs"
    second.close()


def test_repository_lists_workflows_and_filters_by_status(tmp_path):
    repository = WorkflowRepository(tmp_path / "argos.db")
    first = repository.create_workflow(build_workflow("Primeiro"))
    second = repository.create_workflow(build_workflow("Segundo"))
    repository.update_workflow_status(second.id, WorkflowStatus.VALIDATED)

    all_workflows = repository.list_workflows()
    drafts = repository.list_workflows(status=WorkflowStatus.DRAFT)

    assert [item.id for item in all_workflows] == [second.id, first.id]
    assert [item.id for item in drafts] == [first.id]
    repository.close()


def test_repository_updates_workflow_status_and_lifecycle_timestamps(tmp_path):
    repository = WorkflowRepository(tmp_path / "argos.db")
    workflow = repository.create_workflow(build_workflow())

    validated = repository.update_workflow_status(
        workflow.id,
        WorkflowStatus.VALIDATED,
    )
    approved = repository.update_workflow_status(
        workflow.id,
        WorkflowStatus.APPROVED,
    )
    enabled = repository.update_workflow_status(
        workflow.id,
        WorkflowStatus.ENABLED,
    )

    assert validated.status == WorkflowStatus.VALIDATED
    assert approved.approved_at is not None
    assert approved.approved_at.tzinfo == timezone.utc
    assert enabled.status == WorkflowStatus.ENABLED
    assert enabled.enabled_at is not None
    assert enabled.updated_at >= workflow.updated_at
    repository.close()


def test_repository_rejects_invalid_workflow_transition(tmp_path):
    repository = WorkflowRepository(tmp_path / "argos.db")
    workflow = repository.create_workflow(build_workflow())

    with pytest.raises(InvalidWorkflowTransition):
        repository.update_workflow_status(
            workflow.id,
            WorkflowStatus.ENABLED,
        )

    repository.close()


def test_repository_raises_for_missing_workflow(tmp_path):
    repository = WorkflowRepository(tmp_path / "argos.db")

    with pytest.raises(KeyError):
        repository.update_workflow_status(
            "missing",
            WorkflowStatus.VALIDATED,
        )

    repository.close()


def test_repository_persists_and_updates_workflow_run(tmp_path):
    repository = WorkflowRepository(tmp_path / "argos.db")
    workflow = repository.create_workflow(build_workflow())
    run = WorkflowRun(
        workflow_id=workflow.id,
        trigger_event={"path": "C:/Downloads/report.pdf"},
        audit_id="audit-1",
    )

    repository.create_run(run)
    running = repository.update_run_status(run.id, WorkflowRunStatus.RUNNING)
    succeeded = repository.update_run_status(
        run.id,
        WorkflowRunStatus.SUCCEEDED,
    )

    assert running.status == WorkflowRunStatus.RUNNING
    assert succeeded.finished_at is not None
    assert repository.get_run(run.id) == succeeded
    assert repository.list_runs(workflow.id) == [succeeded]
    repository.close()


def test_repository_persists_and_updates_workflow_run_step(tmp_path):
    repository = WorkflowRepository(tmp_path / "argos.db")
    workflow = repository.create_workflow(build_workflow())
    run = repository.create_run(WorkflowRun(workflow_id=workflow.id))
    run_step = WorkflowRunStep(
        run_id=run.id,
        step_id="inspect",
        input_json={"path": "C:/Downloads/report.pdf"},
    )

    repository.create_run_step(run_step)
    running = repository.update_run_step_status(
        run_step.id,
        WorkflowRunStepStatus.RUNNING,
    )
    succeeded = repository.update_run_step_status(
        run_step.id,
        WorkflowRunStepStatus.SUCCEEDED,
        output_json={"mime_type": "application/pdf"},
    )

    assert running.status == WorkflowRunStepStatus.RUNNING
    assert succeeded.output_json == {"mime_type": "application/pdf"}
    assert succeeded.finished_at is not None
    assert repository.get_run_step(run_step.id) == succeeded
    assert repository.list_run_steps(run.id) == [succeeded]
    repository.close()


def test_repository_preserves_run_step_output_when_status_changes(tmp_path):
    repository = WorkflowRepository(tmp_path / "argos.db")
    workflow = repository.create_workflow(build_workflow())
    run = repository.create_run(WorkflowRun(workflow_id=workflow.id))
    run_step = repository.create_run_step(
        WorkflowRunStep(
            run_id=run.id,
            step_id="inspect",
            output_json={"existing": True},
        )
    )

    updated = repository.update_run_step_status(
        run_step.id,
        WorkflowRunStepStatus.RUNNING,
    )

    assert updated.output_json == {"existing": True}
    repository.close()
