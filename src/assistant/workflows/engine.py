from __future__ import annotations

from assistant.workflows.models import (
    Workflow,
    WorkflowRun,
    WorkflowStatus,
)
from assistant.workflows.planner import AdaptativeDynamicWorkflowPlanner
from assistant.workflows.repository import WorkflowRepository
from assistant.workflows.runner import SequentialWorkflowRunner
from assistant.workflows.validator import (
    WorkflowValidationReport,
    WorkflowValidator,
)


class AmbiguousWorkflowId(LookupError):
    pass


class WorkflowNotRunnable(ValueError):
    pass


class WorkflowValidationFailed(ValueError):
    def __init__(self, report: WorkflowValidationReport) -> None:
        self.report = report
        super().__init__("Workflow validation failed.")


class WorkflowEngine:
    def __init__(
        self,
        repository: WorkflowRepository,
        planner: AdaptativeDynamicWorkflowPlanner,
        validator: WorkflowValidator,
        runner: SequentialWorkflowRunner,
    ) -> None:
        self._repository = repository
        self._planner = planner
        self._validator = validator
        self._runner = runner

    def generate(self, description: str) -> Workflow:
        workflow = self._planner.generate(description)
        if workflow.status != WorkflowStatus.DRAFT:
            workflow = workflow.model_copy(
                update={"status": WorkflowStatus.DRAFT}
            )
        return self._repository.create_workflow(workflow)

    def get(self, workflow_id: str) -> Workflow:
        workflow = self._repository.get_workflow(workflow_id)
        if workflow is not None:
            return workflow
        if len(workflow_id) < 8:
            raise KeyError(workflow_id)
        matches = [
            candidate
            for candidate in self._repository.list_workflows()
            if candidate.id.startswith(workflow_id)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AmbiguousWorkflowId(workflow_id)
        raise KeyError(workflow_id)

    def list(
        self,
        status: WorkflowStatus | None = None,
    ) -> list[Workflow]:
        return self._repository.list_workflows(status=status)

    def validate(self, workflow_id: str) -> Workflow:
        workflow = self.get(workflow_id)
        report = self._validator.validate(workflow)
        if not report.ok:
            raise WorkflowValidationFailed(report)
        return self._repository.update_workflow_status(
            workflow.id,
            WorkflowStatus.VALIDATED,
        )

    def approve(self, workflow_id: str) -> Workflow:
        return self._transition(workflow_id, WorkflowStatus.APPROVED)

    def reject(self, workflow_id: str) -> Workflow:
        return self._transition(workflow_id, WorkflowStatus.REJECTED)

    def enable(self, workflow_id: str) -> Workflow:
        return self._transition(workflow_id, WorkflowStatus.ENABLED)

    def disable(self, workflow_id: str) -> Workflow:
        return self._transition(workflow_id, WorkflowStatus.DISABLED)

    def archive(self, workflow_id: str) -> Workflow:
        return self._transition(workflow_id, WorkflowStatus.ARCHIVED)

    def run(
        self,
        workflow_id: str,
        trigger_event: dict | None = None,
    ) -> WorkflowRun:
        workflow = self.get(workflow_id)
        if workflow.status != WorkflowStatus.ENABLED:
            raise WorkflowNotRunnable(
                f"Workflow must be enabled, current status is "
                f"{workflow.status.value}."
            )
        return self._runner.run(workflow, trigger_event=trigger_event)

    def list_runs(self, workflow_id: str) -> list[WorkflowRun]:
        workflow = self.get(workflow_id)
        return self._repository.list_runs(workflow.id)

    def list_run_steps(self, run_id: str):
        return self._repository.list_run_steps(run_id)

    def _transition(
        self,
        workflow_id: str,
        status: WorkflowStatus,
    ) -> Workflow:
        workflow = self.get(workflow_id)
        return self._repository.update_workflow_status(
            workflow.id,
            status,
        )
