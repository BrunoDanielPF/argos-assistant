from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock

from assistant.workflows.models import (
    Workflow,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunStep,
    WorkflowRunStepStatus,
    WorkflowStatus,
    ensure_valid_workflow_transition,
)


class WorkflowRepository:
    def __init__(self, database_file: Path) -> None:
        self._database_file = Path(database_file)
        self._database_file.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self._database_file,
            check_same_thread=False,
        )
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._lock = RLock()
        self._create_schema()

    def _create_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    schema_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    scope_json TEXT,
                    source_prompt TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT,
                    enabled_at TEXT
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    trigger_event_json TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    error TEXT,
                    audit_id TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows(id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS workflow_run_steps (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT,
                    output_json TEXT,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY (run_id) REFERENCES workflow_runs(id)
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflows_status_created
                ON workflows(status, created_at DESC)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow_started
                ON workflow_runs(workflow_id, started_at DESC)
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_workflow_run_steps_run_started
                ON workflow_run_steps(run_id, started_at)
                """
            )

    def create_workflow(self, workflow: Workflow) -> Workflow:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO workflows (
                    id, name, description, schema_version, status,
                    spec_json, scope_json, source_prompt, created_at,
                    updated_at, approved_at, enabled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._workflow_values(workflow),
            )
        return workflow.model_copy(deep=True)

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, name, description, schema_version, status,
                       spec_json, scope_json, source_prompt, created_at,
                       updated_at, approved_at, enabled_at
                FROM workflows
                WHERE id = ?
                """,
                (workflow_id,),
            ).fetchone()
        return self._workflow_from_row(row) if row else None

    def list_workflows(
        self,
        status: WorkflowStatus | None = None,
    ) -> list[Workflow]:
        query = (
            "SELECT id, name, description, schema_version, status, "
            "spec_json, scope_json, source_prompt, created_at, updated_at, "
            "approved_at, enabled_at FROM workflows"
        )
        parameters: tuple = ()
        if status is not None:
            query += " WHERE status = ?"
            parameters = (status.value,)
        query += " ORDER BY created_at DESC, rowid DESC"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        return [self._workflow_from_row(row) for row in rows]

    def update_workflow_status(
        self,
        workflow_id: str,
        status: WorkflowStatus,
    ) -> Workflow:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT status, approved_at, enabled_at FROM workflows WHERE id = ?",
                (workflow_id,),
            ).fetchone()
            if row is None:
                raise KeyError(workflow_id)
            ensure_valid_workflow_transition(WorkflowStatus(row[0]), status)
            now = datetime.now(timezone.utc).isoformat()
            approved_at = now if status == WorkflowStatus.APPROVED else row[1]
            enabled_at = now if status == WorkflowStatus.ENABLED else row[2]
            self._connection.execute(
                """
                UPDATE workflows
                SET status = ?, updated_at = ?, approved_at = ?, enabled_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    now,
                    approved_at,
                    enabled_at,
                    workflow_id,
                ),
            )
        workflow = self.get_workflow(workflow_id)
        assert workflow is not None
        return workflow

    def create_run(self, run: WorkflowRun) -> WorkflowRun:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO workflow_runs (
                    id, workflow_id, status, trigger_event_json, started_at,
                    finished_at, error, audit_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._run_values(run),
            )
        return run.model_copy(deep=True)

    def get_run(self, run_id: str) -> WorkflowRun | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, workflow_id, status, trigger_event_json, started_at,
                       finished_at, error, audit_id
                FROM workflow_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
        return self._run_from_row(row) if row else None

    def list_runs(self, workflow_id: str) -> list[WorkflowRun]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, workflow_id, status, trigger_event_json, started_at,
                       finished_at, error, audit_id
                FROM workflow_runs
                WHERE workflow_id = ?
                ORDER BY started_at DESC, rowid DESC
                """,
                (workflow_id,),
            ).fetchall()
        return [self._run_from_row(row) for row in rows]

    def update_run_status(
        self,
        run_id: str,
        status: WorkflowRunStatus,
        error: str | None = None,
    ) -> WorkflowRun:
        finished_at = (
            datetime.now(timezone.utc).isoformat()
            if status
            in {
                WorkflowRunStatus.SUCCEEDED,
                WorkflowRunStatus.FAILED,
                WorkflowRunStatus.CANCELLED,
                WorkflowRunStatus.BLOCKED,
            }
            else None
        )
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE workflow_runs
                SET status = ?, finished_at = ?, error = ?
                WHERE id = ?
                """,
                (status.value, finished_at, error, run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(run_id)
        run = self.get_run(run_id)
        assert run is not None
        return run

    def create_run_step(self, run_step: WorkflowRunStep) -> WorkflowRunStep:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO workflow_run_steps (
                    id, run_id, step_id, status, input_json, output_json,
                    error, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._run_step_values(run_step),
            )
        return run_step.model_copy(deep=True)

    def get_run_step(self, run_step_id: str) -> WorkflowRunStep | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT id, run_id, step_id, status, input_json, output_json,
                       error, started_at, finished_at
                FROM workflow_run_steps
                WHERE id = ?
                """,
                (run_step_id,),
            ).fetchone()
        return self._run_step_from_row(row) if row else None

    def list_run_steps(self, run_id: str) -> list[WorkflowRunStep]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, run_id, step_id, status, input_json, output_json,
                       error, started_at, finished_at
                FROM workflow_run_steps
                WHERE run_id = ?
                ORDER BY started_at, rowid
                """,
                (run_id,),
            ).fetchall()
        return [self._run_step_from_row(row) for row in rows]

    def update_run_step_status(
        self,
        run_step_id: str,
        status: WorkflowRunStepStatus,
        output_json: dict | None = None,
        error: str | None = None,
    ) -> WorkflowRunStep:
        finished_at = (
            datetime.now(timezone.utc).isoformat()
            if status
            in {
                WorkflowRunStepStatus.SUCCEEDED,
                WorkflowRunStepStatus.FAILED,
                WorkflowRunStepStatus.SKIPPED,
                WorkflowRunStepStatus.CANCELLED,
                WorkflowRunStepStatus.BLOCKED,
            }
            else None
        )
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE workflow_run_steps
                SET status = ?,
                    output_json = COALESCE(?, output_json),
                    error = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    self._dump_json(output_json),
                    error,
                    finished_at,
                    run_step_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(run_step_id)
        run_step = self.get_run_step(run_step_id)
        assert run_step is not None
        return run_step

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @classmethod
    def _workflow_values(cls, workflow: Workflow) -> tuple:
        spec = {
            "trigger": workflow.trigger.model_dump(mode="json"),
            "strategy": workflow.strategy.value,
            "steps": [step.model_dump(mode="json") for step in workflow.steps],
            "policy": workflow.policy.model_dump(mode="json"),
            "budget": workflow.budget.model_dump(mode="json"),
            "metadata": workflow.metadata,
        }
        return (
            workflow.id,
            workflow.name,
            workflow.description,
            workflow.schema_version,
            workflow.status.value,
            cls._dump_json(spec),
            cls._dump_json(workflow.scope),
            workflow.source_prompt,
            workflow.created_at.isoformat(),
            workflow.updated_at.isoformat(),
            workflow.approved_at.isoformat() if workflow.approved_at else None,
            workflow.enabled_at.isoformat() if workflow.enabled_at else None,
        )

    @classmethod
    def _workflow_from_row(cls, row: tuple) -> Workflow:
        spec = json.loads(row[5])
        return Workflow.model_validate(
            {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "schema_version": row[3],
                "status": row[4],
                "trigger": spec["trigger"],
                "strategy": spec["strategy"],
                "steps": spec["steps"],
                "policy": spec["policy"],
                "budget": spec["budget"],
                "scope": json.loads(row[6]) if row[6] else {},
                "created_at": row[8],
                "updated_at": row[9],
                "approved_at": row[10],
                "enabled_at": row[11],
                "source_prompt": row[7],
                "metadata": spec.get("metadata", {}),
            }
        )

    @classmethod
    def _run_values(cls, run: WorkflowRun) -> tuple:
        return (
            run.id,
            run.workflow_id,
            run.status.value,
            cls._dump_json(run.trigger_event),
            run.started_at.isoformat(),
            run.finished_at.isoformat() if run.finished_at else None,
            run.error,
            run.audit_id,
        )

    @staticmethod
    def _run_from_row(row: tuple) -> WorkflowRun:
        return WorkflowRun.model_validate(
            {
                "id": row[0],
                "workflow_id": row[1],
                "status": row[2],
                "trigger_event": json.loads(row[3]) if row[3] else None,
                "started_at": row[4],
                "finished_at": row[5],
                "error": row[6],
                "audit_id": row[7],
            }
        )

    @classmethod
    def _run_step_values(cls, run_step: WorkflowRunStep) -> tuple:
        return (
            run_step.id,
            run_step.run_id,
            run_step.step_id,
            run_step.status.value,
            cls._dump_json(run_step.input_json),
            cls._dump_json(run_step.output_json),
            run_step.error,
            run_step.started_at.isoformat(),
            run_step.finished_at.isoformat() if run_step.finished_at else None,
        )

    @staticmethod
    def _run_step_from_row(row: tuple) -> WorkflowRunStep:
        return WorkflowRunStep.model_validate(
            {
                "id": row[0],
                "run_id": row[1],
                "step_id": row[2],
                "status": row[3],
                "input_json": json.loads(row[4]) if row[4] else None,
                "output_json": json.loads(row[5]) if row[5] else None,
                "error": row[6],
                "started_at": row[7],
                "finished_at": row[8],
            }
        )

    @staticmethod
    def _dump_json(value: dict | None) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
