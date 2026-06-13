# Argos Integrated Gateway Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual terminal verification with a subprocess-backed pytest harness that starts an isolated Argos gateway, exercises chat/approval/workflow flows, captures logs, and drives fixes until predictable failures never become HTTP 500 or raw tracebacks.

**Architecture:** A reusable integration harness will create an isolated `ARGOS_HOME`, laboratory filesystem, fake Ollama endpoint, and real Uvicorn gateway subprocess on a free port. Tests will communicate through `GatewayClient`/HTTP and the real CLI command surface. Production fixes remain in runtime validation, executor error mapping, gateway exception translation, configuration path derivation, and tools CLI registration.

**Tech Stack:** Python 3.12, pytest, FastAPI/Uvicorn, httpx, Typer, SQLite, LangGraph checkpointers.

---

### Task 1: Build The Isolated Gateway Harness

**Files:**
- Create: `tests/integration/argos_gateway_harness.py`
- Create: `tests/integration/gateway_harness_server.py`
- Create: `tests/integration/test_argos_gateway_cli_flows.py`

- [x] Create a temporary laboratory containing two `.txt` files, one `.tmp` file, and `backup/`.
- [x] Start a fake Ollama HTTP server and a real Argos Uvicorn subprocess on free ports.
- [x] Implement `start_gateway`, `stop_gateway`, `send_chat`, `approve_confirmation`, `list_pending_workflows`, `read_gateway_logs`, `assert_no_http_500`, and `assert_no_traceback`.
- [x] Verify the harness can return `current_cwd` and search laboratory files.

### Task 2: Reproduce Predictable Gateway Failures

**Files:**
- Modify: `tests/integration/test_argos_gateway_cli_flows.py`
- Modify: `tests/gateway/test_app.py`
- Modify: `tests/gateway/test_service.py`
- Modify: `tests/test_executor.py`

- [x] Add failing coverage for stale `files.search` confirmations without `root`.
- [x] Add failing coverage for writing to a directory.
- [x] Add failing coverage proving confirmation errors do not produce HTTP 500.
- [x] Capture gateway logs and assert absence of ASGI traceback.

### Task 3: Harden Validation And Error Translation

**Files:**
- Modify: `src/assistant/agent.py`
- Modify: `src/assistant/execution/executor.py`
- Modify: `src/assistant/gateway/service.py`
- Modify: `src/assistant/gateway/app.py`

- [x] Rebind and revalidate confirmation arguments before executor dispatch.
- [x] Convert filesystem `PermissionError`, directory targets, and invalid paths into structured `ExecutionResult`.
- [x] Translate predictable confirmation/workflow exceptions into structured non-500 responses.
- [x] Preserve `error_code` through gateway contracts.

### Task 4: Cover Provisioning Safety End To End

**Files:**
- Modify: `tests/integration/test_argos_gateway_cli_flows.py`
- Modify: `src/assistant/planner.py`
- Modify: `src/assistant/capabilities/provisioning.py`

- [x] Verify metadata creates `pending_approval`, supports `approve_enable_and_run_once`, and is reused.
- [x] Verify environment intent never becomes `file.write` and uses a fake runner.
- [x] Block broad shell capability requests terminally.
- [x] Reject network-plus-write capability requests with a structured reason.

### Task 5: Make ARGOS_HOME And Tools CLI Complete

**Files:**
- Modify: `src/assistant/config.py`
- Modify: `src/assistant/cli.py`
- Modify: `src/assistant/gateway/client.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/integration/test_argos_gateway_cli_flows.py`

- [x] Derive every default database, log, tool, draft, checkpoint, and token path from `ARGOS_HOME`.
- [x] Register `argos tools pending --session <id>`.
- [x] Register `argos tools cancel <workflow_id>`.
- [x] Verify both commands against the isolated gateway.

### Task 6: Full Verification And Delivery

**Files:**
- Modify only files required by failing tests.

- [x] Run `python -m pytest tests/integration/test_argos_gateway_cli_flows.py -q`.
- [x] Run `python -m pytest -q`.
- [x] Run `python -m compileall -q src tests`.
- [x] Run `git diff --check`.
- [x] Run `python -m ruff check src tests`.
- [x] Review captured logs and report reproduced bugs, root causes, files, tests, and remaining failures.
