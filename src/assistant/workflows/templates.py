from assistant.workflows.models import (
    PolicyDecision,
    Workflow,
    WorkflowBudget,
    WorkflowPolicy,
    WorkflowStep,
    WorkflowTrigger,
    WorkflowTriggerType,
)


def pdf_download_workflow(source_prompt: str) -> Workflow:
    return Workflow(
        name="Organizar PDFs baixados",
        description=(
            "Inspeciona novos PDFs, sugere um destino e move somente após "
            "confirmação."
        ),
        trigger=WorkflowTrigger(
            type=WorkflowTriggerType.FILE_CREATED,
            arguments={"path": "~/Downloads", "pattern": "*.pdf"},
        ),
        steps=[
            WorkflowStep(
                id="inspect_pdf",
                name="Inspecionar PDF",
                uses="files.inspect",
                with_args={"path": "${trigger.path}"},
            ),
            WorkflowStep(
                id="suggest_destination",
                name="Sugerir destino",
                uses="files.suggest_destination",
                with_args={"path": "${trigger.path}"},
            ),
            WorkflowStep(
                id="confirm_move",
                name="Confirmar movimentação",
                uses="workflow.ask_confirmation",
                with_args={
                    "message": "Mover o PDF para o destino sugerido?"
                },
                requires_confirmation=True,
            ),
            WorkflowStep(
                id="move_pdf",
                name="Mover PDF",
                uses="files.move",
                with_args={
                    "source": "${trigger.path}",
                    "destination": (
                        "${steps.suggest_destination.output.destination}"
                    ),
                },
                requires_confirmation=True,
            ),
        ],
        policy=WorkflowPolicy(
            actions={
                "files.inspect": PolicyDecision.ALLOW,
                "files.suggest_destination": PolicyDecision.ALLOW,
                "workflow.ask_confirmation": PolicyDecision.CONFIRM,
                "files.move": PolicyDecision.CONFIRM,
            }
        ),
        budget=WorkflowBudget(
            max_steps=4,
            max_runtime_seconds=120,
            max_model_calls=0,
            max_parallel_tasks=1,
        ),
        scope={"root": "~/Downloads"},
        source_prompt=source_prompt,
        metadata={"template": "pdf_download_organization"},
    )


def daily_task_review_workflow(source_prompt: str) -> Workflow:
    return Workflow(
        name="Revisão diária de tarefas",
        description="Notifica o usuário para revisar suas tarefas às 09:00.",
        trigger=WorkflowTrigger(
            type=WorkflowTriggerType.SCHEDULE,
            arguments={
                "time": "09:00",
                "recurrence": "daily",
                "timezone": "local",
            },
        ),
        steps=[
            WorkflowStep(
                id="notify_task_review",
                name="Notificar revisão",
                uses="notification.send",
                with_args={
                    "title": "Argos",
                    "message": "Hora de revisar suas tarefas.",
                },
            )
        ],
        policy=WorkflowPolicy(
            actions={"notification.send": PolicyDecision.ALLOW}
        ),
        budget=WorkflowBudget(
            max_steps=1,
            max_runtime_seconds=30,
            max_model_calls=0,
            max_parallel_tasks=1,
        ),
        source_prompt=source_prompt,
        metadata={"template": "daily_task_review"},
    )


def markdown_organization_workflow(source_prompt: str) -> Workflow:
    return Workflow(
        name="Sugerir organização para Markdown",
        description=(
            "Inspeciona novos arquivos Markdown e sugere uma organização."
        ),
        trigger=WorkflowTrigger(
            type=WorkflowTriggerType.FILE_CREATED,
            arguments={"path": ".", "pattern": "*.md"},
        ),
        steps=[
            WorkflowStep(
                id="inspect_markdown",
                name="Inspecionar Markdown",
                uses="files.inspect",
                with_args={"path": "${trigger.path}"},
            ),
            WorkflowStep(
                id="suggest_destination",
                name="Sugerir organização",
                uses="files.suggest_destination",
                with_args={"path": "${trigger.path}"},
            ),
            WorkflowStep(
                id="confirm_organization",
                name="Confirmar sugestão",
                uses="workflow.ask_confirmation",
                with_args={
                    "message": "Aplicar a organização sugerida?"
                },
                requires_confirmation=True,
            ),
        ],
        policy=WorkflowPolicy(
            actions={
                "files.inspect": PolicyDecision.ALLOW,
                "files.suggest_destination": PolicyDecision.ALLOW,
                "workflow.ask_confirmation": PolicyDecision.CONFIRM,
            }
        ),
        budget=WorkflowBudget(
            max_steps=3,
            max_runtime_seconds=60,
            max_model_calls=0,
            max_parallel_tasks=1,
        ),
        source_prompt=source_prompt,
        metadata={"template": "markdown_organization"},
    )


def job_failure_notification_workflow(source_prompt: str) -> Workflow:
    return Workflow(
        name="Notificar falha de job",
        description="Notifica o usuário quando um job do Argos falhar.",
        trigger=WorkflowTrigger(
            type=WorkflowTriggerType.JOB_FAILED,
            arguments={"source": "argos.jobs"},
        ),
        steps=[
            WorkflowStep(
                id="notify_job_failure",
                name="Notificar falha",
                uses="notification.send",
                with_args={
                    "title": "Argos: job com falha",
                    "message": (
                        "Um job falhou. Consulte os logs para detalhes."
                    ),
                },
            )
        ],
        policy=WorkflowPolicy(
            actions={"notification.send": PolicyDecision.ALLOW}
        ),
        budget=WorkflowBudget(
            max_steps=1,
            max_runtime_seconds=30,
            max_model_calls=0,
            max_parallel_tasks=1,
        ),
        source_prompt=source_prompt,
        metadata={
            "template": "job_failure_notification",
            "integration": "jobs_event_bridge_pending",
        },
    )
