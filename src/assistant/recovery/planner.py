from assistant.recovery.models import (
    FailureEvent,
    FailureType,
    RecoveryPlan,
    RecoveryRisk,
    RecoveryStrategy,
)
from assistant.recovery.policy import RecoveryPolicy


class RecoveryPlanner:
    def __init__(self, policy: RecoveryPolicy | None = None) -> None:
        self._policy = policy or RecoveryPolicy()

    def create_plan(
        self,
        event: FailureEvent,
        *,
        arguments: dict | None = None,
    ) -> RecoveryPlan:
        action = {
            "capability": event.operation,
            "arguments": arguments or {},
        }
        if event.failure_type == FailureType.TIMEOUT:
            decision = self._policy.decide(
                event,
                strategy=RecoveryStrategy.RETRY_WITH_BACKOFF.value,
                attempt=event.attempt,
                action=action,
            )
            if decision.allowed:
                return RecoveryPlan(
                    failure_type=event.failure_type,
                    strategy=RecoveryStrategy.RETRY_WITH_BACKOFF,
                    risk=decision.risk,
                    requires_confirmation=False,
                    max_retries=1,
                    user_message=(
                        "A operacao excedeu o tempo limite. "
                        "Uma unica nova tentativa segura sera feita."
                    ),
                )
            return RecoveryPlan(
                failure_type=event.failure_type,
                strategy=RecoveryStrategy.FALLBACK_TO_PARTIAL_ANSWER,
                risk=decision.risk,
                requires_confirmation=False,
                user_message=(
                    "A operacao excedeu o tempo limite e nao foi repetida "
                    "automaticamente porque a recuperacao nao e de baixo risco."
                ),
            )
        if event.failure_type == FailureType.POLICY_BLOCKED:
            return RecoveryPlan(
                failure_type=event.failure_type,
                strategy=RecoveryStrategy.SUGGEST_SAFE_ALTERNATIVE,
                risk=RecoveryRisk.CRITICAL,
                requires_confirmation=False,
                user_message=(
                    "A acao destrutiva foi bloqueada pela policy e nao sera executada. "
                    "Use uma alternativa de leitura, listagem ou selecao explicita."
                ),
            )
        if event.failure_type == FailureType.NO_RESULTS:
            return RecoveryPlan(
                failure_type=event.failure_type,
                strategy=RecoveryStrategy.FALLBACK_TO_PARTIAL_ANSWER,
                risk=RecoveryRisk.LOW,
                requires_confirmation=False,
                user_message=(
                    "A busca foi concluida sem alterar nada, mas nenhum "
                    "resultado correspondeu aos filtros informados."
                ),
            )
        if event.failure_type in {
            FailureType.UNSUPPORTED_CAPABILITY,
            FailureType.CAPABILITY_GAP,
        }:
            return RecoveryPlan(
                failure_type=event.failure_type,
                strategy=RecoveryStrategy.SUGGEST_SAFE_ALTERNATIVE,
                risk=RecoveryRisk.LOW,
                requires_confirmation=False,
                user_message=(
                    f"O Argos ainda nao oferece suporte a {event.operation}. "
                    "Como alternativa, uma tool local so pode ser criada como "
                    "draft e depois de confirmacao explicita."
                ),
            )
        if event.failure_type == FailureType.INVALID_SCHEMA:
            return RecoveryPlan(
                failure_type=event.failure_type,
                strategy=RecoveryStrategy.REBUILD_CONTEXT,
                risk=RecoveryRisk.LOW,
                requires_confirmation=False,
                user_message=(
                    "Os argumentos do plano sao invalidos. O Argos pode "
                    "propor um plano corrigido, que sera validado novamente "
                    "antes de qualquer confirmacao."
                ),
            )
        if event.failure_type == FailureType.WRONG_INTENT:
            decision = self._policy.decide_action(
                event.operation,
                arguments or {},
            )
            return RecoveryPlan(
                failure_type=event.failure_type,
                strategy=(
                    RecoveryStrategy.DRY_RUN_THEN_CONFIRM
                    if decision.requires_confirmation
                    else RecoveryStrategy.REBUILD_CONTEXT
                ),
                risk=decision.risk,
                requires_confirmation=decision.requires_confirmation,
                user_message=(
                    "O intent selecionado nao corresponde ao pedido. "
                    "O Argos deve replanejar e exigir nova confirmacao "
                    "se o plano corrigido puder alterar recursos."
                ),
            )
        if event.failure_type == FailureType.CONTEXT_AMBIGUITY:
            return RecoveryPlan(
                failure_type=event.failure_type,
                strategy=RecoveryStrategy.REBUILD_CONTEXT,
                risk=RecoveryRisk.LOW,
                requires_confirmation=False,
                user_message=(
                    "O contexto esta ambiguo. Confirme o recurso correto antes "
                    "de qualquer execucao."
                ),
            )
        decision = self._policy.decide_action(event.operation, arguments or {})
        if decision.requires_confirmation:
            return RecoveryPlan(
                failure_type=event.failure_type,
                strategy=RecoveryStrategy.DRY_RUN_THEN_CONFIRM,
                risk=decision.risk,
                requires_confirmation=True,
                user_message=(
                    "A recuperacao pode causar alteracoes. Revise o dry-run "
                    "antes de autorizar."
                ),
            )
        return RecoveryPlan(
            failure_type=event.failure_type,
            strategy=RecoveryStrategy.FALLBACK_TO_PARTIAL_ANSWER,
            risk=decision.risk,
            requires_confirmation=False,
            user_message=(
                "Nao foi possivel concluir a operacao. "
                "O Argos manteve o estado atual e retornou o diagnostico disponivel."
            ),
        )
