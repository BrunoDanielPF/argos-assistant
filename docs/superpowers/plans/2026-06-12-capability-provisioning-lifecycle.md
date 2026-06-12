# Capability Provisioning Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Approve, install, enable, reload, and explicitly retry a safely provisioned local tool.

**Architecture:** Extend `CapabilityProvisioningService` with a lifecycle operation built on `ToolStateStore` and `ToolInstaller`. Let `GatewayService` rebuild only the affected session agent after enablement, then ask the fresh agent to prepare the original action as a normal confirmation.

**Tech Stack:** Python 3.12, Pydantic, pytest, SQLite session confirmations, existing ToolCatalog, ToolInstaller, ToolRunner, audit and recovery infrastructure.

---

### Task 1: Tool Lifecycle

**Files:**
- Modify: `src/assistant/capabilities/provisioning.py`
- Test: `tests/capabilities/test_provisioning.py`

- [x] Add a failing test that transitions a validated draft through approved,
  installed, and enabled only after an explicit lifecycle call.
- [x] Add a failing test proving rejection leaves the tool validated.
- [x] Implement lifecycle orchestration with `ToolInstaller` and audit events.
- [x] Run the provisioning tests until green.

### Task 2: Agent Retry Contract

**Files:**
- Modify: `src/assistant/agent.py`
- Modify: `src/assistant/memory/session.py`
- Test: `tests/capabilities/test_runtime_contracts.py`

- [x] Add failing tests for lifecycle confirmation after draft creation.
- [x] Add failing tests translating the original environment action to
  `local.windows.env_set_user`.
- [x] Add a regression test that records no `file.write` execution.
- [x] Implement special lifecycle confirmation and a method that prepares the
  original action using the fresh registry.

### Task 3: Gateway Reload

**Files:**
- Modify: `src/assistant/gateway/service.py`
- Modify: `src/assistant/runtime/factory.py`
- Test: `tests/gateway/test_service.py`
- Test: `tests/gateway/test_end_to_end.py`

- [x] Add a failing gateway test proving the cached agent is evicted after
  enablement.
- [x] Add a failing e2e test covering environment gap, draft, enable, reload,
  retry confirmation, and fake execution.
- [x] Implement session-scoped agent reload and persist the retry confirmation.
- [x] Audit registry reload and retry confirmation.

### Task 4: Verification

**Files:**
- Test: all touched modules

- [x] Run focused lifecycle and gateway tests.
- [x] Run the complete suite with `PYTHONPATH=.;src`.
- [x] Run Ruff on changed files, compileall, and `git diff --check`.
- [x] Commit only scoped lifecycle files.
