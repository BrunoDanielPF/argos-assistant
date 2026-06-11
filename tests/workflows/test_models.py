from datetime import timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from assistant.workflows.models import (
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
    WorkflowStrategy,
    WorkflowTrigger,
    WorkflowTriggerType,
)


def build_workflow() -> Workflow:
    return Workflow(
        name="Organizar PDFs",
        description="Sugere uma pasta e move o PDF após confirmação.",
        trigger=WorkflowTrigger(
            type=WorkflowTriggerType.FILE_CREATED,
            arguments={"path": "~/Downloads", "pattern": "*.pdf"},
        ),
        steps=[
            WorkflowStep(
                id="inspect",
                name="Inspecionar PDF",
                uses="files.inspect",
                with_args={"path": "${trigger.path}"},
            ),
            WorkflowStep(
                id="move",
                name="Mover PDF",
                uses="files.move",
                with_args={
                    "source": "${trigger.path}",
                    "destination": "${steps.suggest.output.destination}",
                },
                requires_confirmation=True,
            ),
        ],
        policy=WorkflowPolicy(
            default_decision=PolicyDecision.BLOCKED,
            actions={
                "files.inspect": PolicyDecision.ALLOW,
                "files.move": PolicyDecision.CONFIRM,
            },
        ),
        budget=WorkflowBudget(
            max_steps=4,
            max_runtime_seconds=120,
            max_model_calls=1,
            max_parallel_tasks=1,
        ),
        scope={"root": "~/Downloads"},
        source_prompt="quando eu baixar um PDF, sugira mover",
    )


def test_workflow_defaults_to_strict_draft_contract():
    workflow = build_workflow()

    UUID(workflow.id)
    assert workflow.schema_version == "1.0"
    assert workflow.status == WorkflowStatus.DRAFT
    assert workflow.strategy == WorkflowStrategy.SEQUENTIAL
    assert workflow.created_at.tzinfo == timezone.utc
    assert workflow.updated_at.tzinfo == timezone.utc
    assert workflow.approved_at is None
    assert workflow.enabled_at is None
    assert workflow.metadata == {}
    assert workflow.steps[1].timeout_seconds == 60
    assert workflow.steps[1].continue_on_error is False


def test_workflow_rejects_missing_or_non_positive_budget():
    payload = build_workflow().model_dump()
    payload["budget"]["max_steps"] = 0

    with pytest.raises(ValidationError):
        Workflow.model_validate(payload)


def test_workflow_rejects_unknown_fields():
    payload = build_workflow().model_dump()
    payload["generated_code"] = "print('unsafe')"

    with pytest.raises(ValidationError):
        Workflow.model_validate(payload)


def test_run_and_run_step_generate_ids_and_pending_statuses():
    workflow = build_workflow()
    run = WorkflowRun(
        workflow_id=workflow.id,
        trigger_event={"path": "C:/Users/user/Downloads/report.pdf"},
    )
    run_step = WorkflowRunStep(
        run_id=run.id,
        step_id="inspect",
        input_json={"path": "report.pdf"},
    )

    UUID(run.id)
    UUID(run_step.id)
    assert run.status == WorkflowRunStatus.PENDING
    assert run.started_at.tzinfo == timezone.utc
    assert run.finished_at is None
    assert run_step.status == WorkflowRunStepStatus.PENDING
    assert run_step.started_at.tzinfo == timezone.utc
    assert run_step.output_json is None

