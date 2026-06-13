# Adaptive Capability Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely propose and create reviewable local tool drafts for narrow unsupported capabilities.

**Architecture:** Add a dedicated provisioning service around the existing `ToolDraftGenerator`. Integrate it into `AssistantAgent` as an explicit confirmation action and inject it from `RuntimeFactory`.

**Tech Stack:** Python 3.12, Pydantic, pytest, existing Argos tool state, validation, audit, recovery, and gateway confirmation contracts.

---

### Task 1: Provisioning Models And Safe Templates

**Files:**
- Create: `src/assistant/capabilities/provisioning.py`
- Test: `tests/capabilities/test_provisioning.py`

- [ ] Write failing tests for a fixed `git status` proposal, a Windows user
  environment proposal, and destructive rejection.
- [ ] Run `python -m pytest tests/capabilities/test_provisioning.py -q` and
  verify import or assertion failures.
- [ ] Implement strict proposal models, risk checks, safe permissions, and
  calls to `ToolDraftGenerator`.
- [ ] Re-run the focused tests and verify they pass.

### Task 2: Agent Confirmation Flow

**Files:**
- Modify: `src/assistant/agent.py`
- Modify: `src/assistant/recovery/models.py`
- Modify: `src/assistant/recovery/classifier.py`
- Test: `tests/capabilities/test_runtime_contracts.py`
- Test: `tests/recovery/test_functional.py`

- [ ] Write failing tests proving unsupported eligible actions become
  `waiting_confirmation`, rejected confirmations create nothing, approved
  confirmations create a draft, and destructive actions do not provision.
- [ ] Run the focused tests and verify expected failures.
- [ ] Add `capability_gap` classification and special handling for
  `tool.provision_draft` outside the normal capability executor.
- [ ] Record recovery and session audit without retrying the original action.
- [ ] Re-run the focused tests and verify they pass.

### Task 3: Runtime Injection And Tool Audit

**Files:**
- Modify: `src/assistant/runtime/factory.py`
- Modify: `src/assistant/tools/audit.py`
- Test: `tests/runtime/test_factory.py`
- Test: `tests/tools/test_runtime.py`

- [ ] Write failing tests for service injection and proposal/draft audit
  records.
- [ ] Run the focused tests and verify expected failures.
- [ ] Build the service with configured draft, state, audit, and recovery
  paths.
- [ ] Re-run the focused tests and verify they pass.

### Task 4: Verification

**Files:**
- Test: all modified test modules

- [ ] Run focused capability, recovery, runtime, and tool tests.
- [ ] Run `python -m pytest` with `PYTHONPATH=.;src`.
- [ ] Run Ruff, compileall, and `git diff --check`.
- [ ] Exercise the three requested functional prompts without enabling or
  executing generated tools.
