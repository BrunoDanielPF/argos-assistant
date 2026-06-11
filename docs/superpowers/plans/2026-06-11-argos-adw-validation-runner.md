# Argos ADW Validation and Sequential Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic workflow validation, policy evaluation, and auditable sequential execution.

**Architecture:** Validation and policy are pure components with stable typed results. The runner orchestrates injected handlers and persists every run and attempted step through the existing SQLite repository.

**Tech Stack:** Python 3.12, Pydantic 2, sqlite3, pytest

---

### Task 1: Workflow validator

**Files:**
- Create: `src/assistant/workflows/validator.py`
- Create: `tests/workflows/test_validator.py`

- [ ] Write failing tests covering all required fields, unique IDs, known handlers, natural-language draft status, move confirmation, destructive shell, and budget capacity.
- [ ] Run `pytest tests/workflows/test_validator.py -q` and confirm import failure.
- [ ] Implement stable validation findings and mapping/model validation.
- [ ] Run the focused validator tests and confirm they pass.

### Task 2: Policy evaluator

**Files:**
- Create: `src/assistant/workflows/policies.py`
- Create: `tests/workflows/test_policies.py`

- [ ] Write failing tests for allow, confirm, blocked, declarative policy escalation, and all destructive shell patterns.
- [ ] Run `pytest tests/workflows/test_policies.py -q` and confirm import failure.
- [ ] Implement global policy decisions and normalized shell-command detection.
- [ ] Run the focused policy tests and confirm they pass.
- [ ] Commit validator and policy as one security boundary change.

### Task 3: Sequential runner

**Files:**
- Create: `src/assistant/workflows/runner.py`
- Modify: `src/assistant/workflows/models.py`
- Modify: `src/assistant/workflows/repository.py`
- Create: `tests/workflows/test_runner.py`
- Modify: `tests/workflows/test_repository.py`

- [ ] Write failing tests for ordered execution, persisted outputs, max steps, blocking failures, continue-on-error, confirmation, waiting approval, and blocked actions.
- [ ] Run the focused tests and confirm runner import or behavior failure.
- [ ] Add handler result contracts and repository update semantics.
- [ ] Implement sequential execution using injected handlers.
- [ ] Run `pytest tests/workflows -q` and confirm the complete ADW suite passes.
- [ ] Commit the runner and persistence adjustments.

### Task 4: Regression verification

**Files:**
- Modify: `src/assistant/workflows/__init__.py`

- [ ] Export the public validator, policy, and runner contracts.
- [ ] Run `python -m ruff check src/assistant/workflows tests/workflows`.
- [ ] Run `$env:PYTHONPATH='.;src'; python -m pytest -q`.
- [ ] Run `python -m compileall -q src/assistant/workflows tests/workflows`.
- [ ] Run `git diff --check` and verify a clean worktree after commits.

