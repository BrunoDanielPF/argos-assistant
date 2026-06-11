# Argos ADW Models and Persistence Design

## Scope

This first ADW delivery defines the declarative workflow contracts and persists
workflows, runs, and run steps in the shared Argos SQLite database. It does not
execute workflows, evaluate policies, or expose CLI commands.

## Models

`assistant.workflows.models` owns strict Pydantic models for:

- `Workflow`, `WorkflowStep`, `WorkflowBudget`;
- `WorkflowRun`, `WorkflowRunStep`;
- trigger, strategy, policy, workflow status, run status, and run-step status.

All IDs are UUID strings by default and all generated timestamps are timezone
aware UTC values. A workflow defaults to `draft`, a run defaults to `pending`,
and a run step defaults to `pending`.

The trigger is a declarative object with a typed `type` and an `arguments`
mapping. The workflow policy is explicit and contains a default decision plus
per-action decisions. Strategy is restricted to `sequential` in this MVP.

## Persistence

`WorkflowRepository` follows the existing `MemoryRepository` pattern:

- it uses `AppConfig.database_file` through constructor injection;
- enables SQLite WAL and a busy timeout;
- serializes nested workflow configuration into `spec_json`;
- stores scope separately in `scope_json`;
- exposes create, get, list, and status update operations;
- exposes create/get/list/update operations for runs and run steps;
- uses a reentrant lock and closes its connection explicitly.

`spec_json` contains trigger, strategy, steps, policy, budget, and metadata.
Top-level searchable lifecycle fields remain in dedicated columns.

## Lifecycle

Workflow status transitions are deterministic:

```text
draft -> validated | rejected | archived
validated -> approved | rejected | archived
approved -> enabled | rejected | archived
enabled -> disabled | archived
disabled -> enabled | archived
rejected -> archived
archived -> terminal
```

Updating status also updates lifecycle timestamps:

- entering `approved` sets `approved_at`;
- entering `enabled` sets `enabled_at`;
- every status update refreshes `updated_at`.

Invalid transitions raise `InvalidWorkflowTransition`. Missing records raise
`KeyError`.

## Testing

Repository tests use a temporary SQLite file and verify:

- workflow save/load with lossless nested JSON;
- persistence after reopening the database;
- listing all workflows and filtering by status;
- valid lifecycle changes and timestamps;
- invalid lifecycle changes;
- run and run-step persistence as schema coverage.

