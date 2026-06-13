# Adaptive Capability LangGraph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable LangGraph workflow for adaptive capability provisioning while preserving the existing Argos agent, runtime authorities, and explicit approval boundaries.

**Architecture:** `AssistantAgent` reports a structured capability gap. `GatewayService` starts and resumes an `AdaptiveCapabilityGraph` backed by `SqliteSaver`, while Argos SQLite repositories remain authoritative for workflow, approval, tool, audit, and execution state. Graph interrupts represent tool approval and retry confirmation; gateway callbacks reload and execute only within the affected session.

**Tech Stack:** Python 3.12, LangGraph 1.2, `langgraph-checkpoint-sqlite` 3.1, Pydantic 2, SQLite, FastAPI, Typer, Rich, pytest.

---

## File Map

**Create:**

- `src/assistant/capabilities/adaptive_graph.py`: state, stages, nodes, interrupts, resume API.
- `src/assistant/capabilities/workflow_repository.py`: authoritative SQLite workflow records, CAS transitions, TTL queries, and tool leases.
- `src/assistant/capabilities/templates.py`: safe template catalog and future `ToolDefinitionSource` protocol.
- `src/assistant/capabilities/redaction.py`: checkpoint-safe capability payload summaries.
- `src/assistant/capabilities/metrics.py`: injected workflow counter/duration recorder.
- `src/assistant/intent/no_execution.py`: no-execution detection and conceptual-plan rendering.
- `tests/capabilities/test_adaptive_graph.py`: graph transitions, interrupts, resume, rejection, cancellation, and idempotency.
- `tests/capabilities/test_workflow_repository.py`: workflow persistence, limits, CAS, leases, and expiry.
- `tests/intent/test_no_execution.py`: phrase normalization and action suppression.

**Modify:**

- `pyproject.toml`: LangGraph dependencies.
- `src/assistant/config.py`: checkpoint path, TTL, and pending limit.
- `src/assistant/capabilities/provisioning.py`: hash identity, draft reuse, safe lifecycle idempotency, cleanup.
- `src/assistant/tools/generator.py`: draft metadata and validated-draft reuse.
- `src/assistant/tools/state.py`: safe pending-draft removal.
- `src/assistant/agent.py`: structured gap output, root injection, and execution guard.
- `src/assistant/planner.py`: list/search phrases and non-executing conceptual plans.
- `src/assistant/runtime/contracts.py`: public result contract and explicit decisions.
- `src/assistant/runtime/factory.py`: provisioning service and graph dependency builders.
- `src/assistant/gateway/service.py`: graph start/resume, session reload callbacks, list/cancel, cleanup.
- `src/assistant/gateway/app.py`: workflow list/cancel endpoints and shutdown.
- `src/assistant/gateway/client.py`: workflow list/cancel methods and explicit decisions.
- `src/assistant/gateway/process.py`: durable graph and repository wiring.
- `src/assistant/cli.py`: pending/cancel commands and result propagation.
- `src/assistant/cli_ui.py`: neutral pending rendering.
- `src/assistant/observability/events.py`: shared normalized sensitive-key checks.
- `src/assistant/observability/metrics.py`: EventLog-backed capability metric adapter.
- existing focused tests under `tests/capabilities`, `tests/gateway`, `tests/runtime`, and `tests`.

---

### Task 1: Add LangGraph Dependencies and Configuration

**Files:**

- Modify: `pyproject.toml`
- Modify: `src/assistant/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing configuration tests**

Add assertions:

```python
def test_capability_workflow_defaults_use_durable_local_checkpoint():
    config = AppConfig()

    assert config.capability_checkpoint_file == (
        config.argos_home / "capability-checkpoints.db"
    )
    assert config.capability_workflow_ttl_hours == 24
    assert config.max_pending_capability_workflows_per_session == 3
```

- [ ] **Step 2: Run the configuration test and verify RED**

Run:

```powershell
python -m pytest tests/test_config.py -q
```

Expected: failure because the three fields do not exist.

- [ ] **Step 3: Add dependencies and config fields**

Add:

```toml
"langgraph>=1.2,<2",
"langgraph-checkpoint-sqlite>=3.1,<4",
```

Add `Path` and bounded integer fields to `AppConfig`, plus environment
overrides:

```text
ARGOS_CAPABILITY_CHECKPOINT_FILE
ARGOS_CAPABILITY_WORKFLOW_TTL_HOURS
ARGOS_MAX_PENDING_CAPABILITY_WORKFLOWS_PER_SESSION
```

- [ ] **Step 4: Install the editable project and verify imports**

Run:

```powershell
python -m pip install -e ".[dev]"
python -c "from langgraph.checkpoint.sqlite import SqliteSaver; from langgraph.checkpoint.memory import InMemorySaver; print('ok')"
python -m pytest tests/test_config.py -q
```

Expected: imports print `ok`; configuration tests pass.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml src/assistant/config.py tests/test_config.py
git commit -m "build: add adaptive capability graph dependencies"
```

### Task 2: Add Authoritative Workflow Repository

**Files:**

- Create: `src/assistant/capabilities/workflow_repository.py`
- Create: `tests/capabilities/test_workflow_repository.py`

- [ ] **Step 1: Write failing repository tests**

Cover:

```python
def test_repository_persists_workflow_and_lists_pending(tmp_path): ...
def test_repository_rejects_more_than_three_pending_for_session(tmp_path): ...
def test_retry_claim_is_compare_and_set(tmp_path): ...
def test_expired_pending_workflow_is_returned_for_cleanup(tmp_path): ...
def test_tool_lease_has_single_owner(tmp_path): ...
```

Use a fixed clock and assert the persisted record contains `workflow_id`,
`proposal_id`, `tool_definition_hash`, status, and expiry.

- [ ] **Step 2: Run repository tests and verify RED**

Run:

```powershell
python -m pytest tests/capabilities/test_workflow_repository.py -q
```

Expected: import failure for the new repository.

- [ ] **Step 3: Implement models and schema**

Implement:

```python
class CapabilityWorkflowRecord(StrictModel):
    workflow_id: str
    proposal_id: str
    session_id: str
    run_id: str
    requested_capability: str
    tool_name: str
    tool_version: str
    tool_definition_hash: str
    proposal: dict
    original_action: dict
    draft_path: str | None = None
    status: str
    retry_status: str
    created_at: str
    updated_at: str
    expires_at: str
    execution_result: dict | None = None
```

Create `capability_workflows` and `capability_tool_leases` with indexes on
session/status, expiry, and tool identity. Use `RLock`,
`check_same_thread=False`, WAL, busy timeout, JSON serialization, and
`BEGIN IMMEDIATE` for lease/CAS operations.

- [ ] **Step 4: Implement repository operations**

Required methods:

```python
create(record)
load(workflow_id)
find_equivalent_pending(session_id, tool_name, version, definition_hash)
list_pending(session_id=None)
count_pending_tool_approvals(session_id)
transition(workflow_id, expected, target, **updates)
claim_retry(workflow_id)
complete_retry(workflow_id, status, result)
list_expired(now)
acquire_tool_lease(tool_key, owner_workflow_id, expires_at)
release_tool_lease(tool_key, owner_workflow_id)
close()
```

- [ ] **Step 5: Run tests**

```powershell
python -m pytest tests/capabilities/test_workflow_repository.py -q
```

Expected: all repository tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/assistant/capabilities/workflow_repository.py tests/capabilities/test_workflow_repository.py
git commit -m "feat: persist capability workflow lifecycle"
```

### Task 3: Extract Safe Template Source and Definition Identity

**Files:**

- Create: `src/assistant/capabilities/templates.py`
- Modify: `src/assistant/capabilities/provisioning.py`
- Modify: `tests/capabilities/test_provisioning.py`

- [ ] **Step 1: Write failing template and hash tests**

Cover:

```python
def test_safe_catalog_maps_exact_git_status(): ...
def test_safe_catalog_maps_windows_user_environment(): ...
def test_safe_catalog_rejects_generic_shell(): ...
def test_definition_hash_is_stable_across_key_order(): ...
def test_proposal_includes_definition_hash(): ...
```

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests/capabilities/test_provisioning.py -q
```

Expected: missing catalog/hash contract.

- [ ] **Step 3: Implement the extension boundary**

Add:

```python
class ToolDefinitionSource(Protocol):
    def build_candidate(
        self,
        requested_capability: str,
        arguments: dict,
        platform_context: dict,
    ) -> ToolDefinition | None: ...


class SafeToolTemplateCatalog:
    ...
```

Move the two existing definitions into the catalog. Do not add a model-backed
source.

- [ ] **Step 4: Add canonical definition hashing**

Use:

```python
encoded = json.dumps(
    definition.model_dump(mode="json"),
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=True,
).encode("utf-8")
definition_hash = sha256(encoded).hexdigest()
```

Add `tool_definition_hash` to `CapabilityProvisioningProposal`.

- [ ] **Step 5: Verify GREEN**

```powershell
python -m pytest tests/capabilities/test_provisioning.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/assistant/capabilities/templates.py src/assistant/capabilities/provisioning.py tests/capabilities/test_provisioning.py
git commit -m "refactor: isolate safe capability templates"
```

### Task 4: Make Draft Creation Quarantined and Idempotent

**Files:**

- Modify: `src/assistant/tools/generator.py`
- Modify: `src/assistant/tools/state.py`
- Modify: `src/assistant/capabilities/provisioning.py`
- Modify: `tests/tools/test_install_generate.py`
- Modify: `tests/capabilities/test_provisioning.py`

- [ ] **Step 1: Write failing draft reuse and safety tests**

Cover:

```python
def test_generate_reuses_validated_draft_with_same_hash(tmp_path): ...
def test_generate_rejects_same_name_version_with_different_hash(tmp_path): ...
def test_automatic_validation_never_calls_installer_runner_or_subprocess(tmp_path): ...
def test_pending_draft_cleanup_refuses_path_outside_quarantine(tmp_path): ...
```

Inject sentinel functions that fail if handler execution, dependency
installation, subprocess, or network access occurs.

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests/tools/test_install_generate.py tests/capabilities/test_provisioning.py -q
```

- [ ] **Step 3: Add draft metadata**

Write `.argos-draft.json` with:

```json
{
  "proposal_id": "...",
  "tool_definition_hash": "...",
  "created_at": "..."
}
```

Return `GeneratedToolDraft(reused=True|False)` and reuse only a validated
matching draft.

- [ ] **Step 4: Add safe pending cleanup**

Add a state-store method that removes a record only when:

- state is `draft`, `validated`, or `rejected`;
- expected hash matches;
- caller has already validated the quarantine path.

Delete with native `Path`/`shutil` APIs only after resolving and checking the
path is beneath `tool_drafts_dir`.

- [ ] **Step 5: Verify GREEN**

```powershell
python -m pytest tests/tools/test_install_generate.py tests/capabilities/test_provisioning.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/assistant/tools/generator.py src/assistant/tools/state.py src/assistant/capabilities/provisioning.py tests/tools/test_install_generate.py tests/capabilities/test_provisioning.py
git commit -m "feat: reuse quarantined validated tool drafts"
```

### Task 5: Add Checkpoint Redaction

**Files:**

- Create: `src/assistant/capabilities/redaction.py`
- Modify: `src/assistant/observability/events.py`
- Create: `tests/capabilities/test_redaction.py`
- Modify: `tests/observability/test_events.py`

- [ ] **Step 1: Write failing redaction tests**

Cover nested normalized keys and environment variable names:

```python
def test_checkpoint_summary_redacts_nested_credentials(): ...
def test_environment_value_is_redacted_when_name_contains_token(): ...
def test_handler_body_is_omitted_from_checkpoint_summary(): ...
def test_safe_identifiers_remain_visible(): ...
```

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests/capabilities/test_redaction.py tests/observability/test_events.py -q
```

- [ ] **Step 3: Implement shared redaction**

Implement:

```python
redact_capability_payload(value)
summarize_original_action(action)
is_sensitive_key(key)
```

Normalize punctuation and singular/plural credential keys. Special-case
environment actions so `value` is redacted when `name` contains credential
markers.

- [ ] **Step 4: Reuse the normalized check in EventLog**

Keep `EventLog` fail-closed for sensitive detail keys. Do not log prompts or
raw arguments.

- [ ] **Step 5: Verify GREEN**

```powershell
python -m pytest tests/capabilities/test_redaction.py tests/observability/test_events.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/assistant/capabilities/redaction.py src/assistant/observability/events.py tests/capabilities/test_redaction.py tests/observability/test_events.py
git commit -m "fix: redact adaptive capability checkpoints"
```

### Task 6: Implement the Adaptive Capability Graph

**Files:**

- Create: `src/assistant/capabilities/adaptive_graph.py`
- Create: `tests/capabilities/test_adaptive_graph.py`

- [ ] **Step 1: Write failing graph start test**

Use `InMemorySaver` and real provisioning service with temp directories.
Assert a safe gap:

- creates or reuses one validated draft;
- reaches `WAITING_TOOL_APPROVAL`;
- exposes one interrupt;
- contains only JSON-safe redacted state.

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests/capabilities/test_adaptive_graph.py::test_safe_gap_creates_validated_draft_and_interrupts_for_approval -q
```

- [ ] **Step 3: Implement state, stages, and start path**

Define the stage `Literal`/enum and compile:

```python
builder = StateGraph(AdaptiveCapabilityState)
builder.add_edge(START, "detect_gap")
builder.add_edge("detect_gap", "propose_tool")
builder.add_edge("propose_tool", "create_or_reuse_draft")
builder.add_edge("create_or_reuse_draft", "wait_for_tool_approval")
```

The approval node calls:

```python
decision = interrupt(approval_payload)
```

and returns `Command(goto=...)`.

- [ ] **Step 4: Add failing approval/rejection/cancellation tests**

Cover:

```python
Command(resume={"decision": "approve"})
Command(resume={"decision": "reject"})
Command(resume={"decision": "cancel"})
```

Expected stages are `WAITING_RETRY_CONFIRMATION`, `TOOL_REJECTED`, and
`TOOL_APPROVAL_CANCELLED`.

- [ ] **Step 5: Implement enable, reload, and second interrupt**

Inject callbacks:

```python
reload_session_runtime(session_id, enabled_payload)
prepare_retry(session_id, enabled_payload)
execute_retry(session_id, retry_action)
```

After reload, call `interrupt()` with the dry-run and permissions.

- [ ] **Step 6: Add failing retry tests**

Cover approve, reject, cancel, execution success, execution failure, and a
duplicate resume that must not call the executor twice.

- [ ] **Step 7: Implement retry CAS and terminal nodes**

Claim retry in `CapabilityWorkflowRepository` before execution. Return the
stored result when already terminal.

- [ ] **Step 8: Run graph tests**

```powershell
python -m pytest tests/capabilities/test_adaptive_graph.py -q
```

- [ ] **Step 9: Commit**

```powershell
git add src/assistant/capabilities/adaptive_graph.py tests/capabilities/test_adaptive_graph.py
git commit -m "feat: orchestrate capability provisioning with langgraph"
```

### Task 7: Make Tool Enablement Race-Safe and Idempotent

**Files:**

- Modify: `src/assistant/capabilities/provisioning.py`
- Modify: `src/assistant/capabilities/workflow_repository.py`
- Modify: `tests/capabilities/test_provisioning.py`
- Modify: `tests/capabilities/test_workflow_repository.py`

- [ ] **Step 1: Write failing concurrent lifecycle tests**

Use two service calls for the same `tool_name@version` and assert:

- only one installer call;
- both callers receive the same enabled tool;
- no invalid duplicate transition;
- an expired lease may be recovered;
- a live lease owned by another workflow blocks cleanly.

- [ ] **Step 2: Verify RED**

```powershell
python -m pytest tests/capabilities/test_provisioning.py tests/capabilities/test_workflow_repository.py -q
```

- [ ] **Step 3: Add keyed process locks and SQLite leases**

Acquire:

```text
process RLock -> BEGIN IMMEDIATE lease -> re-read tool state
```

Release the lease in `finally`.

- [ ] **Step 4: Make lifecycle transitions idempotent**

Handle `validated`, `approved`, `installed`, and `enabled` explicitly. Check
installed paths before copying and never overwrite mismatched content.

- [ ] **Step 5: Verify GREEN**

```powershell
python -m pytest tests/capabilities/test_provisioning.py tests/capabilities/test_workflow_repository.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/assistant/capabilities/provisioning.py src/assistant/capabilities/workflow_repository.py tests/capabilities/test_provisioning.py tests/capabilities/test_workflow_repository.py
git commit -m "fix: serialize provisioned tool enablement"
```

### Task 8: Formalize Agent and UI Result Contracts

**Files:**

- Modify: `src/assistant/runtime/contracts.py`
- Modify: `src/assistant/cli_ui.py`
- Modify: `src/assistant/cli.py`
- Modify: `tests/runtime/test_contracts.py`
- Modify: `tests/test_cli_ui.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing response-contract tests**

Add:

```python
response = AgentResponse(
    session_id="default",
    run_id="run-1",
    ok=True,
    status="waiting_confirmation",
    result="pending_approval",
    message="Draft validated.",
)
assert response.error_code is None
```

Reject `result="error"` with `ok=True` and reject pending approval with an
`error_code`.

- [ ] **Step 2: Write failing UI tests**

Assert:

- `pending_approval` renders `Aprovacao pendente`, not `Erro`;
- `pending_confirmation` renders `Confirmacao pendente`;
- `success_partial` renders a non-error partial result;
- only `error` renders the red error panel.

- [ ] **Step 3: Verify RED**

```powershell
python -m pytest tests/runtime/test_contracts.py tests/test_cli_ui.py tests/test_cli.py -q
```

- [ ] **Step 4: Implement the result field and compatibility mapping**

Add:

```python
result: Literal[
    "success",
    "success_partial",
    "pending_confirmation",
    "pending_approval",
    "error",
] = "success"
```

Keep transport `status` compatibility. Ensure CLI gateway conversion includes
`status`, `result`, `confirmation`, and `error_code`.

- [ ] **Step 5: Verify GREEN**

```powershell
python -m pytest tests/runtime/test_contracts.py tests/test_cli_ui.py tests/test_cli.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/assistant/runtime/contracts.py src/assistant/cli_ui.py src/assistant/cli.py tests/runtime/test_contracts.py tests/test_cli_ui.py tests/test_cli.py
git commit -m "feat: distinguish pending and error responses"
```

### Task 9: Refactor Agent Gap Output and Fix files.search

**Files:**

- Modify: `src/assistant/agent.py`
- Modify: `src/assistant/planner.py`
- Modify: `tests/capabilities/test_runtime_contracts.py`
- Modify: `tests/test_planner.py`
- Modify: `tests/test_agent.py`

- [ ] **Step 1: Write failing structured-gap test**

Assert the agent returns an internal result containing the requested
capability and original action, without creating a draft or confirmation.

- [ ] **Step 2: Write failing search-language tests**

Cover the four Portuguese forms from the design and assert:

```python
{
    "mode": "action",
    "capability": "files.search",
    "arguments": {
        "root": str(tmp_path),
        "pattern": "*.txt",
        "max_results": 5,
    },
}
```

- [ ] **Step 3: Write failing pre-validation root test**

Use a static planner returning:

```python
{"mode": "action", "capability": "files.search", "arguments": {"pattern": "*.txt"}}
```

Assert registry validation receives `root=current_cwd`.

- [ ] **Step 4: Verify RED**

```powershell
python -m pytest tests/capabilities/test_runtime_contracts.py tests/test_planner.py tests/test_agent.py -q
```

- [ ] **Step 5: Implement structured gap and root injection**

Move automatic provisioning out of `AssistantAgent`. Before the first registry
validation, canonicalize the capability and inject `root` when absent.

- [ ] **Step 6: Expand deterministic search phrases**

Normalize accents with the existing planner helper and support
`liste|listar|mostre|quais` plus `nesta pasta|aqui|pasta atual`.

- [ ] **Step 7: Verify GREEN**

```powershell
python -m pytest tests/capabilities/test_runtime_contracts.py tests/test_planner.py tests/test_agent.py -q
```

- [ ] **Step 8: Commit**

```powershell
git add src/assistant/agent.py src/assistant/planner.py tests/capabilities/test_runtime_contracts.py tests/test_planner.py tests/test_agent.py
git commit -m "fix: normalize capability gaps and local file search"
```

### Task 10: Add NoExecutionGuard Before Planning and Execution

**Files:**

- Create: `src/assistant/intent/no_execution.py`
- Create: `tests/intent/test_no_execution.py`
- Modify: `src/assistant/planner.py`
- Modify: `src/assistant/agent.py`
- Modify: `tests/capabilities/test_runtime_contracts.py`

- [ ] **Step 1: Write failing guard phrase tests**

Parameterize accented and unaccented variants:

```python
[
    "sem executar nada, qual seria o plano para mover arquivos txt para backup?",
    "nao execute, apenas explique como mover arquivos txt para backup",
    "não execute; só me diga o plano",
]
```

- [ ] **Step 2: Write failing defense-in-depth test**

Use a malicious/static planner that returns `file.move_many` and an executor
that raises if called. Assert the response is textual and contains no
confirmation/action.

- [ ] **Step 3: Verify RED**

```powershell
python -m pytest tests/intent/test_no_execution.py tests/capabilities/test_runtime_contracts.py -q
```

- [ ] **Step 4: Implement guard API**

Provide:

```python
matches(user_input) -> bool
strip_directive(user_input) -> str
render_conceptual_plan(plan) -> str
```

The planner uses a sanitized request to derive a plan but returns
`mode="answer"`. The agent checks the guard again before every action and
multi-step plan execution.

- [ ] **Step 5: Verify GREEN**

```powershell
python -m pytest tests/intent/test_no_execution.py tests/capabilities/test_runtime_contracts.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/assistant/intent/no_execution.py src/assistant/planner.py src/assistant/agent.py tests/intent/test_no_execution.py tests/capabilities/test_runtime_contracts.py
git commit -m "fix: prevent execution for explanation-only requests"
```

### Task 11: Coordinate the Graph from GatewayService

**Files:**

- Modify: `src/assistant/runtime/factory.py`
- Modify: `src/assistant/gateway/service.py`
- Modify: `tests/runtime/test_factory.py`
- Modify: `tests/gateway/test_service.py`

- [ ] **Step 1: Write failing gateway start test**

Return a structured gap from a fake agent. Assert gateway:

- starts one graph workflow;
- returns `ok=True`, `result=pending_approval`;
- persists a tool approval confirmation;
- does not expose `error_code`.

- [ ] **Step 2: Write failing resume and reload test**

Approve the tool and assert:

- the graph resumes;
- install/enable occurs once;
- only the session agent cache entry is removed;
- a fresh agent is built;
- the response is a separate retry confirmation.

- [ ] **Step 3: Write failing restart-resume test**

Use a file-backed `SqliteSaver`, create a pending workflow, recreate
`GatewayService`, and approve the existing confirmation. Assert the graph
continues from `WAITING_TOOL_APPROVAL`.

- [ ] **Step 4: Verify RED**

```powershell
python -m pytest tests/runtime/test_factory.py tests/gateway/test_service.py -q
```

- [ ] **Step 5: Add RuntimeFactory builders**

Add focused methods for:

```python
build_capability_provisioning_service()
build_adaptive_capability_graph(checkpointer, workflow_repository, callbacks)
```

`build_agent()` remains responsible for the ordinary agent/runtime.

- [ ] **Step 6: Integrate graph start/resume**

Gateway maps graph interrupts to `SessionRepository` confirmations carrying
`workflow_id`, interrupt kind, and decision target. It resumes with
`Command(resume={"decision": ...})`.

- [ ] **Step 7: Verify GREEN**

```powershell
python -m pytest tests/runtime/test_factory.py tests/gateway/test_service.py -q
```

- [ ] **Step 8: Commit**

```powershell
git add src/assistant/runtime/factory.py src/assistant/gateway/service.py tests/runtime/test_factory.py tests/gateway/test_service.py
git commit -m "feat: coordinate capability graph from gateway"
```

### Task 12: Add Explicit Decisions, Pending APIs, CLI, and TTL Cleanup

**Files:**

- Modify: `src/assistant/runtime/contracts.py`
- Modify: `src/assistant/sessions/repository.py`
- Modify: `src/assistant/gateway/service.py`
- Modify: `src/assistant/gateway/app.py`
- Modify: `src/assistant/gateway/client.py`
- Modify: `src/assistant/gateway/process.py`
- Modify: `src/assistant/cli.py`
- Modify: `tests/sessions/test_repository.py`
- Modify: `tests/gateway/test_app.py`
- Modify: `tests/gateway/test_client.py`
- Modify: `tests/jobs/test_cli.py` or create `tests/tools/test_cli_pending.py`

- [ ] **Step 1: Write failing explicit-decision tests**

Support:

```json
{"decision": "approve"}
{"decision": "reject"}
{"decision": "cancel"}
```

Retain backward compatibility with `{"approved": true|false}` during the
migration.

Add repository tests proving confirmations transition:

```text
pending -> processing -> approved|rejected|cancelled
```

and that a stale `processing` confirmation can be recovered from workflow and
checkpoint state after gateway recreation.

- [ ] **Step 2: Write failing list/cancel API tests**

Assert authenticated endpoints list pending workflows and cancel according to
their current stage.

- [ ] **Step 3: Write failing TTL cleanup tests**

With a fixed clock, assert expired workflows become `WORKFLOW_EXPIRED` and
unreferenced quarantined drafts are removed safely.

- [ ] **Step 4: Write failing CLI tests**

Cover:

```text
argos tools pending --session default
argos tools cancel <workflow_id>
```

- [ ] **Step 5: Verify RED**

```powershell
python -m pytest tests/sessions/test_repository.py tests/gateway/test_app.py tests/gateway/test_client.py tests/tools/test_cli_pending.py -q
```

- [ ] **Step 6: Implement contracts, endpoints, client, and commands**

Do not infer cancellation from transport errors. EOF during an interactive
prompt leaves approval pending; explicit API/CLI cancellation resumes the
graph with `decision=cancel`.

Replace the current one-step `resolve_confirmation` update with:

```python
claim_confirmation(confirmation_id, decision)
finalize_confirmation(confirmation_id, final_status)
recover_processing_confirmations()
```

The gateway finalizes only after graph/domain state is durable.

- [ ] **Step 7: Wire durable production checkpointer**

In `gateway.process`:

```python
connection = sqlite3.connect(
    config.capability_checkpoint_file,
    check_same_thread=False,
)
checkpointer = SqliteSaver(connection)
```

Run cleanup on startup and close graph/repository connections during app
shutdown.

- [ ] **Step 8: Verify GREEN**

```powershell
python -m pytest tests/sessions/test_repository.py tests/gateway/test_app.py tests/gateway/test_client.py tests/tools/test_cli_pending.py -q
```

- [ ] **Step 9: Commit**

```powershell
git add src/assistant/runtime/contracts.py src/assistant/sessions/repository.py src/assistant/gateway/service.py src/assistant/gateway/app.py src/assistant/gateway/client.py src/assistant/gateway/process.py src/assistant/cli.py tests/sessions/test_repository.py tests/gateway/test_app.py tests/gateway/test_client.py tests/tools/test_cli_pending.py
git commit -m "feat: manage pending capability workflows"
```

### Task 13: Add Audit, Metrics, and Secret Regression Coverage

**Files:**

- Create: `src/assistant/capabilities/metrics.py`
- Modify: `src/assistant/observability/metrics.py`
- Modify: `src/assistant/capabilities/adaptive_graph.py`
- Modify: `src/assistant/capabilities/provisioning.py`
- Modify: `src/assistant/gateway/service.py`
- Modify: `tests/capabilities/test_adaptive_graph.py`
- Modify: `tests/gateway/test_end_to_end.py`

- [ ] **Step 1: Write failing audit-sequence test**

Assert the successful Windows environment flow records:

```text
capability_gap_detected
tool_draft_created|tool_draft_reused
tool_validation_completed
tool_approval_pending
tool_approved
tool_enabled
session_registry_reloaded
retry_confirmation_pending
retry_confirmed
capability_action_executed
```

Add rejection, cancellation, expiry, and failure assertions.

- [ ] **Step 2: Write failing secret-storage test**

Use:

```text
name=API_TOKEN
value=super-secret-value
```

Assert the raw value is absent from checkpoint SQLite, event log, tool audit,
and recovery audit.

- [ ] **Step 3: Verify RED**

```powershell
python -m pytest tests/capabilities/test_adaptive_graph.py tests/gateway/test_end_to_end.py -q
```

- [ ] **Step 4: Emit structured events and duration metrics**

Persist identifiers, stage, tool name/version, duration, and result only.
Never include prompts or raw arguments.

Define:

```python
class CapabilityWorkflowMetrics(Protocol):
    def increment(self, name: str, dimensions: dict[str, str]) -> None: ...
    def observe_ms(
        self,
        name: str,
        value: float,
        dimensions: dict[str, str],
    ) -> None: ...
```

Use an EventLog-backed production adapter and an in-memory test recorder.

- [ ] **Step 5: Verify GREEN**

```powershell
python -m pytest tests/capabilities/test_adaptive_graph.py tests/gateway/test_end_to_end.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/assistant/capabilities/metrics.py src/assistant/observability/metrics.py src/assistant/capabilities/adaptive_graph.py src/assistant/capabilities/provisioning.py src/assistant/gateway/service.py tests/capabilities/test_adaptive_graph.py tests/gateway/test_end_to_end.py
git commit -m "feat: audit adaptive capability workflows"
```

### Task 14: Complete End-to-End and Regression Verification

**Files:**

- Modify: `tests/gateway/test_end_to_end.py`
- Modify: `tests/recovery/test_functional.py`

- [ ] **Step 1: Add the final Windows environment E2E**

Use a fake runner and durable file-backed checkpoint. Cover:

```text
request
-> automatic validated draft
-> pending approval
-> approve/enable
-> session reload
-> pending retry confirmation
-> approve retry
-> fake execution
```

Assert `file.write` is never planned or executed.

- [ ] **Step 2: Add functional regressions**

Cover:

- validated draft is not an error;
- workflow resumes after gateway recreation;
- duplicate approval does not reinstall;
- duplicate retry does not execute twice;
- `files.search` missing root uses current cwd;
- all requested Portuguese search forms work;
- no-execution requests return a textual plan without action;
- destructive shell never creates a draft.

- [ ] **Step 3: Run focused suites**

```powershell
python -m pytest tests/capabilities tests/intent tests/gateway tests/runtime tests/recovery/test_functional.py -q
```

Expected: zero failures.

- [ ] **Step 4: Run complete verification**

```powershell
$env:PYTHONPATH='.;src'
python -m pytest -q
python -m compileall -q src tests
git diff --check
```

If Ruff is available:

```powershell
python -m ruff check src tests
```

Expected: zero test, compile, whitespace, or lint failures.

- [ ] **Step 5: Run a gateway smoke test**

Use an isolated `ARGOS_HOME`, start the gateway, submit the environment
request, inspect the pending response, reject it, and confirm no tool is
enabled. Then repeat with the fake-runner test harness for the successful
path.

- [ ] **Step 6: Review scope**

Confirm:

- LangGraph appears only in adaptive capability modules and gateway wiring;
- `AssistantAgent` remains the main planner/runtime;
- no generic shell capability was added;
- no automatic enable or retry exists;
- unrelated `.gitignore` and modern CLI documents are untouched.

- [ ] **Step 7: Commit final integration tests**

```powershell
git add tests/gateway/test_end_to_end.py tests/recovery/test_functional.py
git commit -m "test: cover adaptive capability graph lifecycle"
```
