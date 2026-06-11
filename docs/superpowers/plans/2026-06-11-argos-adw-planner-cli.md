# Argos ADW Heuristic Planner and CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate four safe ADW drafts from natural language and manage their lifecycle and execution through `argos workflows`.

**Architecture:** Template builders create strict workflow models, a model-agnostic heuristic planner selects them, and a workflow engine coordinates persistence, validation, lifecycle, and execution. Typer commands remain presentation adapters over the engine.

**Tech Stack:** Python 3.12, Pydantic 2, Typer, PyYAML, sqlite3, pytest

---

### Task 1: Templates and heuristic planner

**Files:**
- Create: `src/assistant/workflows/templates.py`
- Create: `src/assistant/workflows/planner.py`
- Modify: `src/assistant/workflows/models.py`
- Create: `tests/workflows/test_planner.py`

- [ ] Write failing tests for the four Portuguese descriptions and unsupported descriptions.
- [ ] Run the focused tests and confirm missing planner imports.
- [ ] Add the `job_failed` trigger and implement strict template builders.
- [ ] Implement accent-insensitive deterministic matching.
- [ ] Run the focused tests and commit planner/templates.

### Task 2: Engine, repository operations, and local handlers

**Files:**
- Create: `src/assistant/workflows/engine.py`
- Create: `src/assistant/workflows/handlers.py`
- Modify: `src/assistant/workflows/repository.py`
- Modify: `src/assistant/workflows/runner.py`
- Create: `tests/workflows/test_engine.py`
- Create: `tests/workflows/test_handlers.py`

- [ ] Write failing tests for generate, lifecycle guards, enabled-only run, prefix lookup, archive, and conservative local handlers.
- [ ] Run focused tests and confirm missing APIs.
- [ ] Implement repository lookup/archive support and the workflow engine.
- [ ] Implement local handlers without registering shell.
- [ ] Run focused tests and commit engine/handlers.

### Task 3: Workflow CLI

**Files:**
- Modify: `src/assistant/cli.py`
- Create: `tests/workflows/test_cli.py`

- [ ] Write failing CLI tests for all twelve commands and error paths.
- [ ] Run focused tests and confirm the `workflows` command group is absent.
- [ ] Add repository/engine builders and the Typer subapp.
- [ ] Implement JSON inspect, YAML export, persisted logs, lifecycle commands, archive, and interactive run.
- [ ] Run focused CLI tests and commit the command group.

### Task 4: Public API and regression verification

**Files:**
- Modify: `src/assistant/workflows/__init__.py`

- [ ] Export planner and engine contracts.
- [ ] Run `python -m ruff check src/assistant/workflows tests/workflows`.
- [ ] Run `$env:PYTHONPATH='.;src'; python -m pytest -q`.
- [ ] Run `python -m compileall -q src tests`.
- [ ] Run `git diff --check` and confirm the worktree is clean.

