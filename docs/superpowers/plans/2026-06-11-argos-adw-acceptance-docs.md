# Argos ADW Acceptance Tests and Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all required ADW behaviors executable as acceptance tests, redact sensitive workflow logs, and document the feature.

**Architecture:** A focused acceptance test file composes existing planner, validator, engine, runner, repository, and CLI contracts. A small recursive redaction module protects persisted and rendered workflow audit data.

**Tech Stack:** Python 3.12, Pydantic 2, Typer, pytest, Markdown

---

### Task 1: Acceptance tests and redaction

**Files:**
- Create: `tests/workflows/test_adw_acceptance.py`
- Create: `src/assistant/workflows/redaction.py`
- Modify: `src/assistant/workflows/runner.py`
- Modify: `src/assistant/cli.py`

- [ ] Write the 19 acceptance tests, including nested sensitive fields.
- [ ] Run the focused suite and confirm redaction, rejected-enable, and noop CLI gaps fail.
- [ ] Implement recursive key-based redaction.
- [ ] Apply redaction before persistence and CLI rendering.
- [ ] Run the acceptance and complete ADW suites.
- [ ] Commit tests and security changes.

### Task 2: ADW documentation

**Files:**
- Create: `docs/WORKFLOWS.md`
- Modify: `README.md`

- [ ] Document ADW purpose, declarative contracts, free-script prohibition, lifecycle, CLI, PDF example, and security rules.
- [ ] Add a concise README link to the guide.
- [ ] Check the documentation for placeholders and internal contradictions.
- [ ] Commit documentation.

### Task 3: Regression verification

**Files:**
- No production changes.

- [ ] Run `python -m ruff check src/assistant/cli.py src/assistant/workflows tests/workflows`.
- [ ] Run `$env:PYTHONPATH='.;src'; python -m pytest -q`.
- [ ] Run `python -m compileall -q src tests`.
- [ ] Run `git diff --check` and confirm a clean worktree.

