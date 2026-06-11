# Argos ADW Validation, Policy, and Runner Design

## Scope

This ADW delivery adds deterministic validation, policy evaluation, and
sequential execution over the existing workflow models and SQLite repository.
It does not add workflow CLI commands or built-in filesystem and shell
implementations. Runtime actions are provided through injected handlers.

## Validator

`WorkflowValidator.validate` accepts either a `Workflow` or a raw mapping.
Mappings are required so malformed generated drafts can produce a complete
validation report instead of failing at the first Pydantic parsing error.

The validator reports stable finding codes and checks:

- required schema version, name, trigger, strategy, budget, steps, and policy;
- supported trigger and sequential strategy;
- non-empty steps and unique step IDs;
- known handlers;
- natural-language drafts cannot start enabled;
- `files.move` requires confirmation;
- destructive `shell.run` commands are rejected;
- `max_steps` must cover the declared step count.

Known handlers are:

```text
noop
notification.send
files.inspect
files.suggest_destination
workflow.ask_confirmation
files.move
files.write
shell.run
```

## Policy Evaluator

`WorkflowPolicyEvaluator.evaluate(workflow, step)` returns `PolicyDecision`.
Global safety rules take precedence over the declarative workflow policy:

- destructive actions are always blocked;
- destructive shell commands are always blocked;
- safe built-in read actions default to allow;
- write, move, shell, and workflow enable actions require confirmation;
- unknown actions default to blocked.

The workflow policy may make an action stricter, but it cannot weaken a global
`confirm` or `blocked` decision. `WorkflowStep.requires_confirmation` also
raises an otherwise allowed decision to `confirm`.

Shell detection normalizes casing and whitespace and blocks:

```text
rm -rf
del /s
rmdir /s
format
shutdown
curl ... | bash
Invoke-WebRequest ... | iex
powershell ... iex
```

## Sequential Runner

`SequentialWorkflowRunner` receives:

- a `WorkflowRepository`;
- a mapping from handler name to callable;
- a policy evaluator;
- an optional synchronous confirmer.

The runner:

1. creates a `WorkflowRun` and marks it running;
2. processes steps in declaration order;
3. creates and updates one `WorkflowRunStep` per attempted step;
4. checks policy before calling a handler;
5. stores handler outputs and safe error strings;
6. stops on blocking failures unless `continue_on_error` applies;
7. never runs more than `budget.max_steps`.

Handlers receive a copy of `with_args` and return either a mapping or
`WorkflowHandlerResult`.

Confirmation behavior:

- with a confirmer, rejection cancels the step and run;
- without a confirmer, the step and run become `waiting_approval`;
- blocked steps become `blocked`, and the handler is never called.

`continue_on_error` applies only to handler failures. It never bypasses policy,
approval, or budget enforcement.

## Persistence Adjustments

Run and run-step status updates preserve existing outputs unless a replacement
is explicitly supplied. Terminal states set `finished_at`; waiting and running
states keep it empty.

