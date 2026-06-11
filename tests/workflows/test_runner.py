from assistant.workflows.models import (
    PolicyDecision,
    Workflow,
    WorkflowBudget,
    WorkflowHandlerResult,
    WorkflowPolicy,
    WorkflowRunStatus,
    WorkflowRunStepStatus,
    WorkflowStatus,
    WorkflowStep,
    WorkflowTrigger,
    WorkflowTriggerType,
)
from assistant.workflows.repository import WorkflowRepository
from assistant.workflows.runner import SequentialWorkflowRunner


def build_runner_workflow(
    steps: list[WorkflowStep],
    max_steps: int | None = None,
) -> Workflow:
    return Workflow(
        name="Runner test",
        status=WorkflowStatus.ENABLED,
        trigger=WorkflowTrigger(type=WorkflowTriggerType.MANUAL),
        steps=steps,
        policy=WorkflowPolicy(
            default_decision=PolicyDecision.BLOCKED,
            actions={
                step.uses: PolicyDecision.ALLOW
                for step in steps
                if step.uses == "noop"
            },
        ),
        budget=WorkflowBudget(
            max_steps=max_steps if max_steps is not None else len(steps),
            max_runtime_seconds=60,
            max_model_calls=0,
            max_parallel_tasks=1,
        ),
    )


def create_repository_with_workflow(tmp_path, workflow):
    repository = WorkflowRepository(tmp_path / "argos.db")
    repository.create_workflow(workflow)
    return repository


def test_runner_executes_steps_in_order_and_persists_outputs(tmp_path):
    calls = []
    workflow = build_runner_workflow(
        [
            WorkflowStep(
                id="first",
                name="First",
                uses="noop",
                with_args={"value": 1},
            ),
            WorkflowStep(
                id="second",
                name="Second",
                uses="noop",
                with_args={"value": 2},
            ),
        ]
    )
    repository = create_repository_with_workflow(tmp_path, workflow)

    def noop(arguments):
        calls.append(arguments["value"])
        return {"seen": arguments["value"]}

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"noop": noop},
    ).run(workflow, trigger_event={"source": "manual"})

    steps = repository.list_run_steps(run.id)
    assert calls == [1, 2]
    assert run.status == WorkflowRunStatus.SUCCEEDED
    assert run.trigger_event == {"source": "manual"}
    assert [step.status for step in steps] == [
        WorkflowRunStepStatus.SUCCEEDED,
        WorkflowRunStepStatus.SUCCEEDED,
    ]
    assert [step.output_json for step in steps] == [
        {"seen": 1},
        {"seen": 2},
    ]
    repository.close()


def test_runner_blocks_before_execution_when_step_count_exceeds_budget(tmp_path):
    calls = []
    workflow = build_runner_workflow(
        [
            WorkflowStep(id="first", name="First", uses="noop"),
            WorkflowStep(id="second", name="Second", uses="noop"),
        ],
        max_steps=1,
    )
    repository = create_repository_with_workflow(tmp_path, workflow)

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"noop": lambda arguments: calls.append(arguments)},
    ).run(workflow)

    assert run.status == WorkflowRunStatus.BLOCKED
    assert run.error == "budget_max_steps_exceeded"
    assert calls == []
    assert repository.list_run_steps(run.id) == []
    repository.close()


def test_runner_stops_on_blocking_handler_error(tmp_path):
    calls = []
    workflow = build_runner_workflow(
        [
            WorkflowStep(id="first", name="First", uses="noop"),
            WorkflowStep(id="second", name="Second", uses="noop"),
        ]
    )
    repository = create_repository_with_workflow(tmp_path, workflow)

    def fail_then_record(arguments):
        calls.append(arguments)
        if len(calls) == 1:
            raise RuntimeError("sensitive details")
        return {}

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"noop": fail_then_record},
    ).run(workflow)

    steps = repository.list_run_steps(run.id)
    assert run.status == WorkflowRunStatus.FAILED
    assert run.error == "RuntimeError"
    assert len(calls) == 1
    assert len(steps) == 1
    assert steps[0].status == WorkflowRunStepStatus.FAILED
    assert steps[0].error == "RuntimeError"
    repository.close()


def test_runner_continues_after_non_blocking_handler_error(tmp_path):
    calls = []
    workflow = build_runner_workflow(
        [
            WorkflowStep(
                id="first",
                name="First",
                uses="noop",
                continue_on_error=True,
            ),
            WorkflowStep(id="second", name="Second", uses="noop"),
        ]
    )
    repository = create_repository_with_workflow(tmp_path, workflow)

    def fail_then_succeed(arguments):
        calls.append(arguments)
        if len(calls) == 1:
            return WorkflowHandlerResult(ok=False, error="expected_failure")
        return {"ok": True}

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"noop": fail_then_succeed},
    ).run(workflow)

    steps = repository.list_run_steps(run.id)
    assert run.status == WorkflowRunStatus.SUCCEEDED
    assert len(calls) == 2
    assert [step.status for step in steps] == [
        WorkflowRunStepStatus.FAILED,
        WorkflowRunStepStatus.SUCCEEDED,
    ]
    assert steps[0].error == "expected_failure"
    repository.close()


def test_runner_executes_confirmed_step(tmp_path):
    calls = []
    confirmations = []
    step = WorkflowStep(
        id="move",
        name="Move",
        uses="files.move",
        with_args={"source": "a.pdf", "destination": "docs/a.pdf"},
        requires_confirmation=True,
    )
    workflow = build_runner_workflow([step])
    workflow.policy.actions["files.move"] = PolicyDecision.CONFIRM
    repository = create_repository_with_workflow(tmp_path, workflow)

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"files.move": lambda arguments: calls.append(arguments) or {}},
        confirmer=lambda handler, arguments: (
            confirmations.append((handler, arguments)) or True
        ),
    ).run(workflow)

    assert run.status == WorkflowRunStatus.SUCCEEDED
    assert calls == [step.with_args]
    assert confirmations == [("files.move", step.with_args)]
    repository.close()


def test_runner_waits_for_approval_without_confirmer(tmp_path):
    calls = []
    step = WorkflowStep(
        id="move",
        name="Move",
        uses="files.move",
        requires_confirmation=True,
    )
    workflow = build_runner_workflow([step])
    workflow.policy.actions["files.move"] = PolicyDecision.CONFIRM
    repository = create_repository_with_workflow(tmp_path, workflow)

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"files.move": lambda arguments: calls.append(arguments)},
    ).run(workflow)

    run_steps = repository.list_run_steps(run.id)
    assert run.status == WorkflowRunStatus.WAITING_APPROVAL
    assert run.finished_at is None
    assert calls == []
    assert run_steps[0].status == WorkflowRunStepStatus.WAITING_APPROVAL
    repository.close()


def test_runner_cancels_when_confirmation_is_rejected(tmp_path):
    calls = []
    step = WorkflowStep(
        id="move",
        name="Move",
        uses="files.move",
        requires_confirmation=True,
    )
    workflow = build_runner_workflow([step])
    workflow.policy.actions["files.move"] = PolicyDecision.CONFIRM
    repository = create_repository_with_workflow(tmp_path, workflow)

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"files.move": lambda arguments: calls.append(arguments)},
        confirmer=lambda handler, arguments: False,
    ).run(workflow)

    run_steps = repository.list_run_steps(run.id)
    assert run.status == WorkflowRunStatus.CANCELLED
    assert calls == []
    assert run_steps[0].status == WorkflowRunStepStatus.CANCELLED
    repository.close()


def test_runner_never_executes_blocked_action(tmp_path):
    calls = []
    step = WorkflowStep(
        id="shell",
        name="Destructive shell",
        uses="shell.run",
        with_args={"command": "rm -rf ./data"},
        requires_confirmation=True,
    )
    workflow = build_runner_workflow([step])
    workflow.policy.actions["shell.run"] = PolicyDecision.CONFIRM
    repository = create_repository_with_workflow(tmp_path, workflow)

    run = SequentialWorkflowRunner(
        repository=repository,
        handlers={"shell.run": lambda arguments: calls.append(arguments)},
        confirmer=lambda handler, arguments: True,
    ).run(workflow)

    run_steps = repository.list_run_steps(run.id)
    assert run.status == WorkflowRunStatus.BLOCKED
    assert run.error == "policy_blocked"
    assert calls == []
    assert run_steps[0].status == WorkflowRunStepStatus.BLOCKED
    repository.close()
