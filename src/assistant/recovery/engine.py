from assistant.recovery.classifier import FailureClassifier
from assistant.recovery.dry_run import DryRunBuilder
from assistant.recovery.models import (
    RecoveryAttempt,
    RecoveryOutcome,
    RecoveryStrategy,
)
from assistant.recovery.planner import RecoveryPlanner
from assistant.recovery.repository import RecoveryRepository


class RecoveryEngine:
    def __init__(
        self,
        classifier: FailureClassifier | None = None,
        planner: RecoveryPlanner | None = None,
        dry_run_builder: DryRunBuilder | None = None,
        repository: RecoveryRepository | None = None,
    ) -> None:
        self._classifier = classifier or FailureClassifier()
        self._planner = planner or RecoveryPlanner()
        self._dry_run_builder = dry_run_builder or DryRunBuilder()
        self._repository = repository

    def handle_failure(
        self,
        *,
        source: str,
        operation: str,
        message: str,
        arguments: dict | None = None,
        error_code: str | None = None,
        exception: Exception | None = None,
        metadata: dict | None = None,
        attempt: int = 0,
    ) -> RecoveryOutcome:
        event = self._classifier.classify(
            source=source,
            operation=operation,
            message=message,
            error_code=error_code,
            exception=exception,
            metadata=metadata,
            attempt=attempt,
        )
        plan = self._planner.create_plan(event, arguments=arguments)
        dry_run = None
        if plan.strategy in {
            RecoveryStrategy.DRY_RUN_THEN_CONFIRM,
            RecoveryStrategy.SUGGEST_SAFE_ALTERNATIVE,
        }:
            dry_run = self._dry_run_builder.build(
                operation,
                arguments or {},
            )
        outcome = RecoveryOutcome(
            event=event,
            plan=plan,
            dry_run=dry_run,
            status=(
                "blocked"
                if dry_run is not None and not dry_run.can_execute
                else "planned"
            ),
        )
        if self._repository is not None:
            self._repository.write(outcome)
        return outcome

    def preview_action(self, capability: str, arguments: dict):
        return self._dry_run_builder.build(capability, arguments)

    def record_attempt(
        self,
        outcome: RecoveryOutcome,
        *,
        attempt: int,
        succeeded: bool,
        message: str,
    ) -> RecoveryAttempt:
        record = RecoveryAttempt(
            failure_event_id=outcome.event.id,
            strategy=outcome.plan.strategy,
            attempt=attempt,
            succeeded=succeeded,
            message=message,
        )
        if self._repository is not None:
            self._repository.write_attempt(record)
        return record
