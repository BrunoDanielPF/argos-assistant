# Argos ADW Heuristic Planner and CLI Design

## Scope

This delivery adds four deterministic natural-language workflow templates and
the complete `argos workflows` command group. The planner remains independent
from Ollama and other model providers.

## Heuristic Planner

`AdaptativeDynamicWorkflowPlanner.generate(description)` normalizes casing,
spacing, and accents, then selects one of four templates:

1. downloaded PDF organization;
2. daily task review at 09:00;
3. Markdown-file organization;
4. job-failure notification.

Every generated workflow:

- has status `draft`;
- retains the original description in `source_prompt`;
- uses sequential strategy;
- declares an explicit policy and mandatory budget;
- contains only known handlers.

Unknown descriptions raise `UnsupportedWorkflowDescription`. The planner does
not call a model and does not persist anything by itself.

`job_failed` is added as a declarative trigger type. The job worker integration
is intentionally deferred; metadata marks the template as awaiting the event
bridge.

## Workflow Engine

`WorkflowEngine` coordinates planner, repository, validator, and runner:

- `generate` creates and persists a draft;
- `validate` validates a draft and transitions it to `validated`;
- `approve` only transitions `validated` workflows;
- `enable` only transitions `approved` workflows;
- `disable`, `reject`, and `archive` use repository lifecycle rules;
- `run` requires an `enabled` workflow.

The engine contains no Typer or console code.

## Local Handlers

The CLI runner receives a conservative local handler registry:

- `noop`;
- `notification.send`;
- `files.inspect`;
- `files.suggest_destination`;
- `workflow.ask_confirmation`;
- `files.move`.

`shell.run` is not registered. `files.move` uses `shutil.move` only after the
runner policy and CLI confirmation succeed. Destination suggestions do not
move files and stay under the source file's user-visible directory tree.

`workflow.ask_confirmation` is a no-op approval checkpoint. Its approval does
not authorize a later sensitive step; `files.move` requests its own
confirmation.

## CLI

The `workflows` Typer subapp provides:

```text
list
generate
inspect
validate
approve
reject
enable
disable
run
logs
delete
export
```

Workflow IDs accept a complete UUID or a unique prefix of at least eight
characters.

- `inspect` emits formatted JSON.
- `logs` emits persisted runs and run-step details.
- `delete` archives instead of deleting.
- `export` writes YAML to stdout.
- `run` uses the existing CLI confirmation style. Non-interactive execution
  leaves confirmation-required runs in `waiting_approval`.

## Error Handling

Missing and ambiguous IDs return exit code 1. Invalid lifecycle transitions and
validation findings are printed without tracebacks. Handler errors are stored
as safe error codes by the runner.

