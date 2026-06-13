# Adaptive Capability LangGraph Design

## Status

Approved for implementation on 2026-06-13.

This document supersedes the orchestration portions of:

- `2026-06-12-adaptive-capability-provisioning-design.md`
- `2026-06-12-capability-provisioning-lifecycle-design.md`

The existing tool lifecycle, validator, policy, registry, catalog, runner, and
audit components remain authoritative.

## Goal

Use LangGraph only to orchestrate the persistent, resumable lifecycle of an
adaptive capability:

```text
capability_gap
-> auto_create_and_validate_draft
-> WAITING_TOOL_APPROVAL
-> enable_after_approval
-> reload_session_runtime
-> WAITING_RETRY_CONFIRMATION
-> execute_after_confirmation
```

The Argos agent remains responsible for planning and detecting unsupported
capabilities. The gateway owns workflow creation, human decisions, session
runtime reload, and workflow resumption.

## Non-Goals

- Do not replace `AssistantAgent` or the general runtime with LangGraph.
- Do not implement broad `shell.run`.
- Do not enable a generated tool automatically.
- Do not execute the original action without a separate retry confirmation.
- Do not treat LangGraph checkpoints as the source of truth for tools,
  approvals, audit, or execution runs.
- Do not generate arbitrary model-authored tools in this MVP.

## Dependencies

Production uses:

```python
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
```

`SqliteSaver` is provided by the separate
`langgraph-checkpoint-sqlite` package. The production connection is opened
with `check_same_thread=False`; `SqliteSaver` supplies its own synchronization.

The implementation will use these compatible dependency ranges:

```toml
"langgraph>=1.2,<2",
"langgraph-checkpoint-sqlite>=3.1,<4",
```

Unit tests may compile the same graph with:

```python
from langgraph.checkpoint.memory import InMemorySaver
```

The durable checkpoint database is separate from the Argos source-of-truth
database:

```text
~/.argos/capability-checkpoints.db
```

## Architecture

### AssistantAgent

The agent detects an unsupported capability after planning and returns an
internal `capability_gap` result containing:

- requested capability;
- user goal;
- extracted arguments;
- platform and path context;
- original action.

The agent does not create, install, enable, or retry the tool. In direct mode,
where no gateway coordinator exists, it returns a clean capability-gap answer.

### GatewayService

The gateway intercepts a provisionable capability gap and starts exactly one
adaptive workflow for the request. It converts graph interrupts into persisted
Argos confirmations and public `AgentResponse` values.

The gateway supplies graph callbacks for:

- rebuilding only the affected session agent;
- preparing a retry against the rebuilt registry and executor;
- executing the confirmed retry through the normal agent/runtime path.

### AdaptiveCapabilityGraph

`AdaptiveCapabilityGraph` is a focused wrapper around a compiled `StateGraph`.
It owns transitions and interrupts but delegates all domain decisions and side
effects.

Nodes:

1. `detect_gap`
2. `propose_tool`
3. `create_or_reuse_draft`
4. `wait_for_tool_approval`
5. `enable_tool`
6. `reload_session_runtime`
7. `wait_for_retry_confirmation`
8. `execute_original_action`
9. terminal rejection, cancellation, and failure nodes

### CapabilityProvisioningService

The service remains the domain authority for proposals, drafts, installation,
enablement, permission summaries, and retry action translation.

For the MVP it receives candidates only from a `SafeToolTemplateCatalog`.
Allowed templates are:

- exact `git status` -> `local.git.status`;
- Windows user environment variable update ->
  `local.windows.env_set_user`.

The architecture exposes a `ToolDefinitionSource` protocol. A future
model-backed source may provide a `ToolDefinition`, but it must pass the same:

- static validation;
- capability policy;
- permission allowlist;
- sandbox preflight;
- explicit human approval.

No model-backed source is implemented now.

### CapabilityWorkflowRepository

A new repository in the existing Argos SQLite database is the source of truth
for workflow identity and durable domain state. It stores:

- `workflow_id`;
- `proposal_id`;
- `session_id` and originating `run_id`;
- requested capability;
- tool name, version, and definition hash;
- proposal and original action required for retry;
- draft path and tool lifecycle status;
- approval and retry decision status;
- timestamps and expiry;
- execution outcome reference.

The LangGraph checkpoint stores only transient orchestration state and
references to these records.

### Confirmation Persistence

`SessionRepository` confirmations gain workflow metadata and a two-phase
decision lifecycle:

```text
pending -> processing -> approved|rejected|cancelled
```

The gateway first claims a pending confirmation as `processing`, resumes the
graph, persists the resulting workflow state/next confirmation, and only then
finalizes the original decision. If the process stops after the claim,
startup/resume logic can recover a stale `processing` record by consulting the
authoritative workflow and LangGraph checkpoint.

A confirmation is never finalized before the graph transition and associated
domain effects have a durable outcome.

## State Model

### Workflow Stages

```text
CAPABILITY_GAP_DETECTED
TOOL_PROPOSED
TOOL_DRAFT_CREATED
WAITING_TOOL_APPROVAL
TOOL_ENABLED
RUNTIME_RELOADED
WAITING_RETRY_CONFIRMATION
ACTION_EXECUTED
ACTION_FAILED
TOOL_REJECTED
TOOL_APPROVAL_CANCELLED
RETRY_REJECTED
RETRY_CANCELLED
WORKFLOW_EXPIRED
```

### Transitions

```text
CAPABILITY_GAP_DETECTED -> TOOL_PROPOSED
TOOL_PROPOSED -> TOOL_DRAFT_CREATED
TOOL_DRAFT_CREATED -> WAITING_TOOL_APPROVAL

WAITING_TOOL_APPROVAL -> TOOL_ENABLED
WAITING_TOOL_APPROVAL -> TOOL_REJECTED
WAITING_TOOL_APPROVAL -> TOOL_APPROVAL_CANCELLED
WAITING_TOOL_APPROVAL -> WORKFLOW_EXPIRED

TOOL_ENABLED -> RUNTIME_RELOADED
RUNTIME_RELOADED -> WAITING_RETRY_CONFIRMATION

WAITING_RETRY_CONFIRMATION -> ACTION_EXECUTED
WAITING_RETRY_CONFIRMATION -> ACTION_FAILED
WAITING_RETRY_CONFIRMATION -> RETRY_REJECTED
WAITING_RETRY_CONFIRMATION -> RETRY_CANCELLED
WAITING_RETRY_CONFIRMATION -> WORKFLOW_EXPIRED
```

### JSON-Safe Checkpoint State

Checkpoint state contains primitive JSON-compatible values only:

```python
class AdaptiveCapabilityState(TypedDict, total=False):
    workflow_id: str
    proposal_id: str
    session_id: str
    run_id: str
    stage: str
    requested_capability: str
    tool_name: str
    tool_version: str
    tool_definition_hash: str
    draft_path: str
    permissions: list[str]
    original_action_ref: str
    original_action_summary: dict
    created_at: str
    updated_at: str
    expires_at: str
    error_code: str | None
    message: str
```

The checkpoint never stores handler source, raw secrets, tokens, passwords, or
full sensitive arguments.

## Human-in-the-Loop

### Tool Approval Interrupt

The graph pauses in `WAITING_TOOL_APPROVAL` with:

```json
{
  "kind": "tool_approval",
  "workflow_id": "...",
  "tool_name": "local.windows.env_set_user",
  "version": "1.0.0",
  "draft_path": ".../tool-drafts/local.windows.env_set_user/1.0.0",
  "permissions": [
    "filesystem_write:none",
    "network:none",
    "subprocess:none"
  ],
  "question": "Aprovar, instalar e habilitar esta tool local?"
}
```

Resume values use an explicit decision:

```json
{"decision": "approve"}
{"decision": "reject"}
{"decision": "cancel"}
```

### Retry Confirmation Interrupt

After enablement and session reload, the graph pauses in
`WAITING_RETRY_CONFIRMATION` with:

- action summary;
- dry-run;
- permission summary;
- explicit retry question.

Only `{"decision": "approve"}` can reach execution.

## Automatic Draft Safety

Draft creation is automatic only after a safe allowlisted proposal.

The draft:

- is created under `tool-drafts`;
- starts as `draft`, is statically validated, and ends as `validated` or
  `rejected`;
- is never installed or enabled during automatic creation;
- never imports or executes `handler.py`;
- never creates a virtual environment;
- never installs dependencies;
- never invokes subprocesses;
- never accesses the network.

The validator parses source with `ast`, validates manifests and JSON schemas,
and checks permission policy. Tests inject sentinels proving no runner,
installer, subprocess, or network client is called.

## Idempotency and Concurrency

### Identifiers

- `proposal_id`: UUID generated when a safe proposal is created.
- `workflow_id`: UUID generated by the gateway for the lifecycle.
- `tool_definition_hash`: SHA-256 of canonical JSON from `ToolDefinition`.

Canonical JSON uses sorted keys and compact separators.

### Draft Reuse

Before generation, the service searches for the same:

```text
tool_name + version + tool_definition_hash
```

If a quarantined draft is still `validated`, it is reused. A metadata file
inside the draft records the hash and creation timestamp. A different hash for
the same name/version is a conflict and does not overwrite the existing draft.

At most one draft workflow may start from one user message. A session may have
at most three active `WAITING_TOOL_APPROVAL` workflows.

### Install and Enable Lock

Install/enable acquires a lease keyed by `tool_name@version` in the Argos
SQLite database using `BEGIN IMMEDIATE`, plus a process-local keyed `RLock`.
The lease has an owner workflow and expiry.

Inside the lock, the service re-reads `ToolStateStore`:

- `enabled` returns the existing enabled record;
- `installed` transitions only to `enabled`;
- `validated` follows approve, install, enable;
- incompatible states return a structured lifecycle error.

The lock is released in `finally`.

### Retry Idempotency

The workflow repository uses compare-and-set transitions:

```text
pending -> executing -> executed|failed
```

Only the transaction that changes `pending` to `executing` may invoke the
runner. Duplicate confirmations return the stored result and do not execute
again.

## Persistence and Redaction

The Argos repositories remain authoritative:

- `ToolStateStore`: tool lifecycle state;
- `CapabilityWorkflowRepository`: workflow and retry domain state;
- `SessionRepository`: confirmations and session snapshots;
- `ToolAuditLog`: tool lifecycle audit;
- `RecoveryRepository`: capability-gap recovery;
- runner audit: execution start and completion.

LangGraph persists only transient workflow stage and safe references.

Before checkpoint or audit persistence:

- recursively redact normalized secret, token, password, API key, private key,
  and credential keys;
- redact environment variable values when the variable name indicates a
  credential;
- omit handler source and complete user prompts;
- store hashes and identifiers instead of sensitive definitions.

## TTL and Pending Management

Defaults:

- workflow TTL: 24 hours;
- maximum pending tool approvals per session: 3.

Cleanup runs at gateway startup and lazily before workflow start/list/resume.

Expired workflows transition to `WORKFLOW_EXPIRED`. Quarantined drafts are
deleted only when:

- no active workflow references them;
- the tool is still `draft`, `validated`, or `rejected`;
- the draft has exceeded TTL;
- the path resolves under the configured `tool-drafts` root.

The state-store record is removed only for a matching pending draft hash.

Gateway API:

```text
GET  /v1/capability-workflows?session_id=<id>&status=pending
POST /v1/capability-workflows/<workflow_id>/cancel
```

CLI:

```text
argos tools pending --session <id>
argos tools cancel <workflow_id>
```

Cancellation maps to `TOOL_APPROVAL_CANCELLED` or `RETRY_CANCELLED` according
to the current stage.

## Response and UI Contract

`AgentResponse` gains:

```python
result: Literal[
    "success",
    "success_partial",
    "pending_confirmation",
    "pending_approval",
    "error",
]
```

The existing transport `status` remains temporarily compatible with
`completed` and `waiting_confirmation`.

Required behavior:

- validated draft waiting for approval:
  `ok=True`, `result="pending_approval"`, no `error_code`;
- ordinary action confirmation:
  `ok=True`, `result="pending_confirmation"`;
- tool enabled and waiting for retry:
  `ok=True`, `result="pending_confirmation"`;
- completed action:
  `ok=True`, `result="success"`;
- capability gap without a safe template:
  `ok=False`, `result="error"`, `error_code="capability_gap"`;
- real generation, validation, install, reload, or execution failure:
  `ok=False`, `result="error"`.

The CLI UI renders `pending_approval` and `pending_confirmation` as neutral
pending states, never as `Erro`.

## Parallel Runtime Corrections

### files.search Root

Before initial registry validation, `AssistantAgent` injects:

```python
root = context["current_cwd"] or context["default_search_root"]
```

when the canonical capability is `files.search` and `root` is absent.

The deterministic planner recognizes:

- `liste os arquivos txt nesta pasta`;
- `listar arquivos .txt aqui`;
- `mostre os arquivos txt na pasta atual`;
- `quais arquivos txt existem aqui`.

### NoExecutionGuard

`NoExecutionGuard` recognizes normalized variants of:

- `sem executar nada`;
- `nao execute`;
- `não execute`;
- `apenas explique`;
- `so me diga o plano`;
- `só me diga o plano`.

It runs:

1. before the normal planner path, producing a textual conceptual plan;
2. immediately before every action or plan execution as defense in depth.

No guarded request may reach policy confirmation, executor, tool runner, or
capability provisioning.

## Audit and Metrics

Structured events:

- `capability_gap_detected`;
- `tool_draft_created` or `tool_draft_reused`;
- `tool_validation_completed`;
- `tool_approval_pending`;
- `tool_approved`;
- `tool_rejected`;
- `tool_approval_cancelled`;
- `tool_enabled`;
- `session_registry_reloaded`;
- `retry_confirmation_pending`;
- `retry_confirmed`;
- `retry_rejected`;
- `retry_cancelled`;
- `capability_action_executed`;
- `capability_action_failed`;
- `capability_workflow_expired`.

Metrics contain only counts, durations, stage, capability name, tool name,
version, and result. They never include prompts or raw arguments.

For the MVP, metrics are emitted through an injected
`CapabilityWorkflowMetrics` recorder. The production adapter writes safe
counter and duration events to `EventLog`; unit tests use an in-memory recorder.
This keeps telemetry independent from graph state and allows a future metrics
backend without changing workflow nodes.

## Verification

The implementation is accepted when:

1. a validated draft renders as `pending_approval`, not error;
2. workflow state survives gateway recreation with `SqliteSaver`;
3. tool approval resumes the graph and reloads only the affected session;
4. retry requires a new interrupt and confirmation;
5. rejection and cancellation reach distinct terminal stages;
6. duplicate approval and retry do not duplicate side effects;
7. a validated equivalent draft is reused;
8. pending limits and TTL cleanup are enforced;
9. checkpoint and audit data contain no test secrets;
10. environment-variable intent never becomes `file.write`;
11. missing `files.search.root` is filled before validation;
12. no-execution requests return text without any action;
13. all existing tests continue to pass.

## References

- LangGraph interrupts:
  <https://docs.langchain.com/oss/python/langgraph/interrupts>
- LangGraph checkpointers:
  <https://docs.langchain.com/oss/python/langgraph/checkpointers>
- SQLite checkpointer package:
  <https://pypi.org/project/langgraph-checkpoint-sqlite/>
