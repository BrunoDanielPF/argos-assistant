from collections.abc import Callable, Mapping
from uuid import uuid4

from assistant.workflows.models import (
    PolicyDecision,
    Workflow,
    WorkflowHandlerResult,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunStep,
    WorkflowRunStepStatus,
)
from assistant.workflows.policies import WorkflowPolicyEvaluator
from assistant.workflows.repository import WorkflowRepository


WorkflowHandler = Callable[[dict], dict | WorkflowHandlerResult]
WorkflowConfirmer = Callable[[str, dict], bool]


class SequentialWorkflowRunner:
    def __init__(
        self,
        repository: WorkflowRepository,
        handlers: Mapping[str, WorkflowHandler],
        policy_evaluator: WorkflowPolicyEvaluator | None = None,
        confirmer: WorkflowConfirmer | None = None,
    ) -> None:
        self._repository = repository
        self._handlers = dict(handlers)
        self._policy_evaluator = policy_evaluator or WorkflowPolicyEvaluator()
        self._confirmer = confirmer

    def run(
        self,
        workflow: Workflow,
        trigger_event: dict | None = None,
    ) -> WorkflowRun:
        run = self._repository.create_run(
            WorkflowRun(
                workflow_id=workflow.id,
                trigger_event=(
                    dict(trigger_event) if trigger_event is not None else None
                ),
                audit_id=str(uuid4()),
            )
        )
        run = self._repository.update_run_status(
            run.id,
            WorkflowRunStatus.RUNNING,
        )

        if len(workflow.steps) > workflow.budget.max_steps:
            return self._repository.update_run_status(
                run.id,
                WorkflowRunStatus.BLOCKED,
                error="budget_max_steps_exceeded",
            )

        for step in workflow.steps:
            arguments = dict(step.with_args)
            run_step = self._repository.create_run_step(
                WorkflowRunStep(
                    run_id=run.id,
                    step_id=step.id,
                    input_json=arguments,
                )
            )
            decision = self._policy_evaluator.evaluate(workflow, step)

            if decision == PolicyDecision.BLOCKED:
                self._repository.update_run_step_status(
                    run_step.id,
                    WorkflowRunStepStatus.BLOCKED,
                    error="policy_blocked",
                )
                return self._repository.update_run_status(
                    run.id,
                    WorkflowRunStatus.BLOCKED,
                    error="policy_blocked",
                )

            if decision == PolicyDecision.CONFIRM:
                confirmation_result = self._resolve_confirmation(
                    step.uses,
                    arguments,
                )
                if confirmation_result is None:
                    self._repository.update_run_step_status(
                        run_step.id,
                        WorkflowRunStepStatus.WAITING_APPROVAL,
                    )
                    return self._repository.update_run_status(
                        run.id,
                        WorkflowRunStatus.WAITING_APPROVAL,
                    )
                if not confirmation_result:
                    self._repository.update_run_step_status(
                        run_step.id,
                        WorkflowRunStepStatus.CANCELLED,
                        error="confirmation_rejected",
                    )
                    return self._repository.update_run_status(
                        run.id,
                        WorkflowRunStatus.CANCELLED,
                        error="confirmation_rejected",
                    )

            self._repository.update_run_step_status(
                run_step.id,
                WorkflowRunStepStatus.RUNNING,
            )
            result = self._execute_handler(step.uses, arguments)
            if result.ok:
                self._repository.update_run_step_status(
                    run_step.id,
                    WorkflowRunStepStatus.SUCCEEDED,
                    output_json=result.output,
                )
                continue

            error = result.error or "handler_failed"
            self._repository.update_run_step_status(
                run_step.id,
                WorkflowRunStepStatus.FAILED,
                output_json=result.output,
                error=error,
            )
            if not step.continue_on_error:
                return self._repository.update_run_status(
                    run.id,
                    WorkflowRunStatus.FAILED,
                    error=error,
                )

        return self._repository.update_run_status(
            run.id,
            WorkflowRunStatus.SUCCEEDED,
        )

    def _resolve_confirmation(
        self,
        handler_name: str,
        arguments: dict,
    ) -> bool | None:
        if self._confirmer is None:
            return None
        try:
            return bool(self._confirmer(handler_name, dict(arguments)))
        except Exception:
            return False

    def _execute_handler(
        self,
        handler_name: str,
        arguments: dict,
    ) -> WorkflowHandlerResult:
        handler = self._handlers.get(handler_name)
        if handler is None:
            return WorkflowHandlerResult(
                ok=False,
                error="handler_not_registered",
            )
        try:
            result = handler(dict(arguments))
        except Exception as exc:
            return WorkflowHandlerResult(
                ok=False,
                error=type(exc).__name__,
            )
        if isinstance(result, WorkflowHandlerResult):
            return result
        if isinstance(result, dict):
            return WorkflowHandlerResult(output=result)
        return WorkflowHandlerResult(
            ok=False,
            error="handler_invalid_result",
        )
