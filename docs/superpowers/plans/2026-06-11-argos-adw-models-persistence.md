# Argos ADW Models and Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add strict ADW domain models and durable SQLite persistence for workflows, workflow runs, and workflow run steps.

**Architecture:** A focused `assistant.workflows` package owns the contracts and repository. Nested declarative workflow data is stored as JSON while lifecycle fields remain queryable columns in the shared Argos database.

**Tech Stack:** Python 3.12, Pydantic 2, sqlite3, pytest

---

### Task 1: Define ADW models

**Files:**
- Create: `src/assistant/workflows/__init__.py`
- Create: `src/assistant/workflows/models.py`
- Test: `tests/workflows/test_models.py`

- [ ] Write model tests asserting strict parsing, defaults, enums, UUID IDs, UTC timestamps, and required positive budgets.
- [ ] Run `pytest tests/workflows/test_models.py -q` and confirm imports fail because the package does not exist.
- [ ] Implement the workflow, step, budget, run, run-step, trigger, policy, strategy, and status models.
- [ ] Run `pytest tests/workflows/test_models.py -q` and confirm all model tests pass.

### Task 2: Persist workflows and lifecycle

**Files:**
- Create: `src/assistant/workflows/repository.py`
- Test: `tests/workflows/test_repository.py`

- [ ] Write repository tests for create, get, reopen, list, status filtering, valid transitions, invalid transitions, and lifecycle timestamps.
- [ ] Run `pytest tests/workflows/test_repository.py -q` and confirm repository imports or calls fail.
- [ ] Implement the `workflows` table, JSON serialization, lookup, listing, and guarded status transitions.
- [ ] Run `pytest tests/workflows/test_repository.py -q` and confirm workflow persistence tests pass.

### Task 3: Persist runs and run steps

**Files:**
- Modify: `src/assistant/workflows/repository.py`
- Modify: `tests/workflows/test_repository.py`

- [ ] Add failing tests for creating, loading, listing, and updating `WorkflowRun` and `WorkflowRunStep`.
- [ ] Run the focused tests and confirm failure because run persistence is missing.
- [ ] Implement `workflow_runs` and `workflow_run_steps` storage and status updates.
- [ ] Run `pytest tests/workflows -q` and confirm the ADW suite passes.

### Task 4: Regression verification

**Files:**
- No production changes.

- [ ] Run `pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Commit only the ADW models, persistence, tests, and documentation.

