import re

from assistant.workflows.models import (
    PolicyDecision,
    Workflow,
    WorkflowStep,
)


MINIMUM_POLICY = {
    "noop": PolicyDecision.ALLOW,
    "notification.send": PolicyDecision.ALLOW,
    "files.inspect": PolicyDecision.ALLOW,
    "files.suggest_destination": PolicyDecision.ALLOW,
    "workflow.ask_confirmation": PolicyDecision.CONFIRM,
    "files.move": PolicyDecision.CONFIRM,
    "files.write": PolicyDecision.CONFIRM,
    "shell.run": PolicyDecision.CONFIRM,
    "workflow.enable": PolicyDecision.CONFIRM,
    "destructive_action": PolicyDecision.BLOCKED,
}

_DECISION_RANK = {
    PolicyDecision.ALLOW: 0,
    PolicyDecision.CONFIRM: 1,
    PolicyDecision.BLOCKED: 2,
}

_DESTRUCTIVE_SHELL_PATTERNS = (
    re.compile(r"(?:^|[;&|]\s*)rm\s+-[a-z]*r[a-z]*f\b", re.IGNORECASE),
    re.compile(r"(?:^|[;&|]\s*)del\s+/s\b", re.IGNORECASE),
    re.compile(r"(?:^|[;&|]\s*)rmdir\s+/s\b", re.IGNORECASE),
    re.compile(r"(?:^|[;&|]\s*)format(?:\.com)?(?:\s|$)", re.IGNORECASE),
    re.compile(r"(?:^|[;&|]\s*)shutdown(?:\.exe)?(?:\s|$)", re.IGNORECASE),
    re.compile(r"\bcurl(?:\.exe)?\b[^|]*\|\s*(?:ba)?sh\b", re.IGNORECASE),
    re.compile(
        r"\b(?:invoke-webrequest|iwr)\b[^|]*\|\s*(?:invoke-expression|iex)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bpowershell(?:\.exe)?\b.*\b(?:invoke-expression|iex)\b",
        re.IGNORECASE,
    ),
)


def is_destructive_shell_command(command: object) -> bool:
    if not isinstance(command, str) or not command.strip():
        return False
    normalized = " ".join(command.split())
    return any(pattern.search(normalized) for pattern in _DESTRUCTIVE_SHELL_PATTERNS)


class WorkflowPolicyEvaluator:
    def evaluate(
        self,
        workflow: Workflow,
        step: WorkflowStep,
    ) -> PolicyDecision:
        if step.uses == "shell.run" and is_destructive_shell_command(
            step.with_args.get("command")
        ):
            return PolicyDecision.BLOCKED

        minimum = MINIMUM_POLICY.get(
            step.uses,
            PolicyDecision.BLOCKED,
        )
        declared = workflow.policy.actions.get(step.uses, minimum)
        decision = max(
            (minimum, declared),
            key=lambda item: _DECISION_RANK[item],
        )
        if (
            step.requires_confirmation
            and decision == PolicyDecision.ALLOW
        ):
            return PolicyDecision.CONFIRM
        return decision
