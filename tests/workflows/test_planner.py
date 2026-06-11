import pytest

from assistant.workflows.models import (
    PolicyDecision,
    WorkflowStatus,
    WorkflowTriggerType,
)
from assistant.workflows.planner import (
    AdaptativeDynamicWorkflowPlanner,
    UnsupportedWorkflowDescription,
)
from assistant.workflows.validator import WorkflowValidator


def test_planner_generates_pdf_download_workflow():
    prompt = "quando eu baixar um PDF, sugira mover para a pasta correta"

    workflow = AdaptativeDynamicWorkflowPlanner().generate(prompt)

    assert workflow.status == WorkflowStatus.DRAFT
    assert workflow.trigger.type == WorkflowTriggerType.FILE_CREATED
    assert workflow.trigger.arguments == {
        "path": "~/Downloads",
        "pattern": "*.pdf",
    }
    assert [step.uses for step in workflow.steps] == [
        "files.inspect",
        "files.suggest_destination",
        "workflow.ask_confirmation",
        "files.move",
    ]
    assert workflow.steps[-1].requires_confirmation is True
    assert workflow.policy.actions["files.move"] == PolicyDecision.CONFIRM
    assert workflow.budget.max_steps >= len(workflow.steps)
    assert workflow.source_prompt == prompt
    assert WorkflowValidator().validate(workflow).ok is True


def test_planner_generates_daily_task_review_workflow():
    workflow = AdaptativeDynamicWorkflowPlanner().generate(
        "todo dia às 9h, revise minhas tarefas"
    )

    assert workflow.status == WorkflowStatus.DRAFT
    assert workflow.trigger.type == WorkflowTriggerType.SCHEDULE
    assert workflow.trigger.arguments["time"] == "09:00"
    assert workflow.trigger.arguments["recurrence"] == "daily"
    assert workflow.steps[0].uses == "notification.send"
    assert workflow.budget.max_steps >= 1


def test_planner_generates_markdown_organization_workflow():
    workflow = AdaptativeDynamicWorkflowPlanner().generate(
        "quando eu criar um .md, sugira organização"
    )

    assert workflow.status == WorkflowStatus.DRAFT
    assert workflow.trigger.type == WorkflowTriggerType.FILE_CREATED
    assert workflow.trigger.arguments["pattern"] == "*.md"
    assert [step.uses for step in workflow.steps] == [
        "files.inspect",
        "files.suggest_destination",
        "workflow.ask_confirmation",
    ]


def test_planner_generates_job_failure_notification_workflow():
    workflow = AdaptativeDynamicWorkflowPlanner().generate(
        "quando um job falhar, me avise"
    )

    assert workflow.status == WorkflowStatus.DRAFT
    assert workflow.trigger.type == WorkflowTriggerType.JOB_FAILED
    assert workflow.steps[0].uses == "notification.send"
    assert workflow.metadata["integration"] == "jobs_event_bridge_pending"


def test_planner_matching_is_case_and_accent_insensitive():
    workflow = AdaptativeDynamicWorkflowPlanner().generate(
        "TODO DIA AS 9H, REVISE MINHAS TAREFAS"
    )

    assert workflow.trigger.type == WorkflowTriggerType.SCHEDULE


def test_planner_rejects_unsupported_description():
    with pytest.raises(UnsupportedWorkflowDescription):
        AdaptativeDynamicWorkflowPlanner().generate(
            "monitore qualquer coisa e faça o melhor possível"
        )
