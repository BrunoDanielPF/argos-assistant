from assistant.capabilities.registry import (
    CapabilityRegistry,
    build_default_registry,
)
from assistant.execution.policy import decide_policy
from assistant.recovery.models import DryRunPlan, RecoveryRisk


class DryRunBuilder:
    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
    ) -> None:
        self._registry = registry or build_default_registry()

    def build(self, capability: str, arguments: dict) -> DryRunPlan:
        validation = self._registry.validate(capability, arguments)
        if not validation.ok:
            return DryRunPlan(
                action=capability,
                risk=RecoveryRisk.MEDIUM,
                requires_confirmation=False,
                expected_result=validation.message or "Action is not executable.",
                can_execute=False,
                error_code=validation.error_code,
            )

        assert validation.capability is not None
        assert validation.arguments is not None
        canonical = validation.capability.name
        normalized_arguments = validation.arguments
        policy = decide_policy(
            canonical,
            normalized_arguments,
            registry=self._registry,
        )
        resources = self._resources(canonical, normalized_arguments)
        permissions = self._permissions(canonical, resources)
        risk = self._risk(canonical, policy)
        allowed = policy != "blocked"
        resource_summary = (
            ", ".join(resources) if resources else "os recursos informados"
        )
        if canonical == "file.delete_dry_run":
            expected = (
                "Esta simulacao apenas listaria os arquivos correspondentes "
                f"em {resource_summary}. Nenhum arquivo seria alterado."
            )
        elif canonical == "file.delete_one" and allowed:
            expected = (
                f"A exclusao real excluiria {resource_summary}, somente "
                "depois de confirmacao explicita."
            )
        elif canonical == "file.move_many" and allowed:
            expected = (
                f"A movimentacao alteraria {resource_summary}, somente "
                "depois de confirmacao explicita."
            )
        elif allowed:
            expected = (
                f"A acao {canonical} seria executada sobre "
                f"{resource_summary}."
            )
        else:
            expected = (
                f"A acao {canonical} foi bloqueada pela policy e nao pode "
                "ser executada."
            )
        return DryRunPlan(
            action=canonical,
            resources_affected=resources,
            risk=risk,
            permissions_required=permissions,
            requires_confirmation=policy == "confirm",
            expected_result=expected,
            can_execute=allowed,
            error_code="policy_blocked" if not allowed else None,
        )

    @staticmethod
    def _resources(capability: str, arguments: dict) -> list[str]:
        resources = []
        for key in ("path", "source_root", "destination", "root"):
            value = arguments.get(key)
            if isinstance(value, str) and value.strip() and value not in resources:
                resources.append(value)
        for value in arguments.get("sources", []):
            if isinstance(value, str) and value not in resources:
                resources.append(value)
        return resources

    @staticmethod
    def _permissions(capability: str, resources: list[str]) -> list[str]:
        if capability in {
            "file.read",
            "file.open",
            "file.delete_dry_run",
            "files.search",
        }:
            return [f"read:{resource}" for resource in resources]
        if capability in {
            "file.create",
            "file.write",
            "file.create_directory",
            "file.delete_one",
            "file.move_many",
        }:
            return [f"write:{resource}" for resource in resources]
        return [f"execute:{capability}"]

    @staticmethod
    def _risk(capability: str, policy: str) -> RecoveryRisk:
        if policy == "blocked":
            return RecoveryRisk.CRITICAL
        if capability in {"file.delete_one", "file.move_many"}:
            return RecoveryRisk.HIGH
        if policy == "confirm":
            return RecoveryRisk.MEDIUM
        return RecoveryRisk.LOW
