from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from assistant.workflows.models import (
    Workflow,
    WorkflowStatus,
    WorkflowStrategy,
    WorkflowTriggerType,
)
from assistant.workflows.policies import is_destructive_shell_command


KNOWN_HANDLERS = {
    "noop",
    "notification.send",
    "files.inspect",
    "files.suggest_destination",
    "workflow.ask_confirmation",
    "files.move",
    "files.write",
    "shell.run",
}


@dataclass(frozen=True)
class WorkflowValidationFinding:
    code: str
    message: str
    path: str | None = None


@dataclass
class WorkflowValidationReport:
    findings: list[WorkflowValidationFinding] = field(default_factory=list)
    workflow: Workflow | None = None

    @property
    def ok(self) -> bool:
        return not self.findings


class WorkflowValidator:
    def validate(
        self,
        candidate: Workflow | dict[str, Any],
    ) -> WorkflowValidationReport:
        if isinstance(candidate, Workflow):
            payload = candidate.model_dump(mode="json")
            workflow = candidate
        elif isinstance(candidate, dict):
            payload = candidate
            workflow = self._parse_workflow(payload)
        else:
            return WorkflowValidationReport(
                findings=[
                    WorkflowValidationFinding(
                        "workflow_invalid",
                        "Workflow must be an object.",
                    )
                ]
            )

        findings = self._required_findings(payload)
        findings.extend(self._semantic_findings(payload))

        if workflow is None and not findings:
            findings.append(
                WorkflowValidationFinding(
                    "workflow_invalid",
                    "Workflow does not match the declarative schema.",
                )
            )
        return WorkflowValidationReport(
            findings=self._deduplicate(findings),
            workflow=workflow if not findings else None,
        )

    @staticmethod
    def _parse_workflow(payload: dict[str, Any]) -> Workflow | None:
        try:
            return Workflow.model_validate(payload)
        except ValidationError:
            return None

    @staticmethod
    def _required_findings(
        payload: dict[str, Any],
    ) -> list[WorkflowValidationFinding]:
        findings = []
        required = (
            ("schema_version", "schema_version_required"),
            ("name", "name_required"),
            ("trigger", "trigger_required"),
            ("strategy", "strategy_required"),
            ("budget", "budget_required"),
            ("steps", "steps_required"),
            ("policy", "policy_required"),
        )
        for field_name, code in required:
            if field_name not in payload or payload[field_name] is None:
                findings.append(
                    WorkflowValidationFinding(
                        code,
                        f"{field_name} is required.",
                        field_name,
                    )
                )
        if "name" in payload and not str(payload.get("name", "")).strip():
            findings.append(
                WorkflowValidationFinding(
                    "name_required",
                    "name is required.",
                    "name",
                )
            )
        return findings

    def _semantic_findings(
        self,
        payload: dict[str, Any],
    ) -> list[WorkflowValidationFinding]:
        findings = []
        trigger = payload.get("trigger")
        if trigger is not None and not self._valid_trigger(trigger):
            findings.append(
                WorkflowValidationFinding(
                    "trigger_invalid",
                    "trigger must use a supported trigger type.",
                    "trigger",
                )
            )

        strategy = payload.get("strategy")
        if strategy is not None and strategy != WorkflowStrategy.SEQUENTIAL.value:
            findings.append(
                WorkflowValidationFinding(
                    "strategy_invalid",
                    "Only the sequential strategy is supported.",
                    "strategy",
                )
            )

        steps = payload.get("steps")
        if isinstance(steps, list):
            if not steps:
                findings.append(
                    WorkflowValidationFinding(
                        "steps_empty",
                        "Workflow must declare at least one step.",
                        "steps",
                    )
                )
            findings.extend(self._step_findings(steps))

        if (
            payload.get("source_prompt")
            and payload.get("status", WorkflowStatus.DRAFT.value)
            != WorkflowStatus.DRAFT.value
        ):
            findings.append(
                WorkflowValidationFinding(
                    "generated_workflow_must_be_draft",
                    "A workflow generated from natural language must start as draft.",
                    "status",
                )
            )

        budget = payload.get("budget")
        if isinstance(budget, dict) and isinstance(steps, list):
            max_steps = budget.get("max_steps")
            if isinstance(max_steps, int) and max_steps < len(steps):
                findings.append(
                    WorkflowValidationFinding(
                        "budget_max_steps_too_small",
                        "budget.max_steps cannot be smaller than the step count.",
                        "budget.max_steps",
                    )
                )
        return findings

    @staticmethod
    def _valid_trigger(trigger: object) -> bool:
        if not isinstance(trigger, dict):
            return False
        try:
            WorkflowTriggerType(trigger.get("type"))
        except (TypeError, ValueError):
            return False
        arguments = trigger.get("arguments", {})
        return isinstance(arguments, dict)

    @staticmethod
    def _step_findings(
        steps: list,
    ) -> list[WorkflowValidationFinding]:
        findings = []
        seen_ids: set[str] = set()
        for index, step in enumerate(steps):
            path = f"steps.{index}"
            if not isinstance(step, dict):
                findings.append(
                    WorkflowValidationFinding(
                        "step_invalid",
                        "Each step must be an object.",
                        path,
                    )
                )
                continue
            step_id = step.get("id")
            if isinstance(step_id, str) and step_id:
                if step_id in seen_ids:
                    findings.append(
                        WorkflowValidationFinding(
                            "step_id_duplicate",
                            f"Duplicate step id: {step_id}.",
                            f"{path}.id",
                        )
                    )
                seen_ids.add(step_id)
            handler = step.get("uses")
            if handler not in KNOWN_HANDLERS:
                findings.append(
                    WorkflowValidationFinding(
                        "handler_unknown",
                        f"Unknown workflow handler: {handler}.",
                        f"{path}.uses",
                    )
                )
            if handler == "files.move":
                requires_confirmation = bool(
                    step.get("requires_confirmation", False)
                )
                if not requires_confirmation:
                    findings.append(
                        WorkflowValidationFinding(
                            "files_move_requires_confirmation",
                            "files.move must require confirmation.",
                            f"{path}.requires_confirmation",
                        )
                    )
            if handler == "shell.run":
                with_args = step.get("with_args", {})
                command = (
                    with_args.get("command")
                    if isinstance(with_args, dict)
                    else None
                )
                if is_destructive_shell_command(command):
                    findings.append(
                        WorkflowValidationFinding(
                            "shell_command_destructive",
                            "Destructive shell commands are blocked.",
                            f"{path}.with_args.command",
                        )
                    )
        return findings

    @staticmethod
    def _deduplicate(
        findings: list[WorkflowValidationFinding],
    ) -> list[WorkflowValidationFinding]:
        unique = []
        seen = set()
        for finding in findings:
            key = (finding.code, finding.path)
            if key not in seen:
                seen.add(key)
                unique.append(finding)
        return unique
