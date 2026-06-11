import re
import unicodedata

from assistant.workflows.models import Workflow
from assistant.workflows.templates import (
    daily_task_review_workflow,
    job_failure_notification_workflow,
    markdown_organization_workflow,
    pdf_download_workflow,
)


class UnsupportedWorkflowDescription(ValueError):
    pass


class AdaptativeDynamicWorkflowPlanner:
    def generate(self, description: str) -> Workflow:
        if not isinstance(description, str) or not description.strip():
            raise UnsupportedWorkflowDescription(
                "Workflow description cannot be empty."
            )
        normalized = self._normalize(description)

        if self._matches_pdf_download(normalized):
            return pdf_download_workflow(description)
        if self._matches_daily_task_review(normalized):
            return daily_task_review_workflow(description)
        if self._matches_markdown_organization(normalized):
            return markdown_organization_workflow(description)
        if self._matches_job_failure(normalized):
            return job_failure_notification_workflow(description)
        raise UnsupportedWorkflowDescription(
            "No safe heuristic workflow template matched the description."
        )

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        without_accents = "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        )
        lowered = without_accents.casefold()
        return re.sub(r"\s+", " ", lowered).strip()

    @staticmethod
    def _matches_pdf_download(value: str) -> bool:
        return (
            "pdf" in value
            and any(term in value for term in ("baixar", "download"))
            and any(term in value for term in ("mover", "pasta correta"))
        )

    @staticmethod
    def _matches_daily_task_review(value: str) -> bool:
        return (
            "todo dia" in value
            and any(term in value for term in ("9h", "09:00", "9:00"))
            and "tarefa" in value
            and any(term in value for term in ("revise", "revisar"))
        )

    @staticmethod
    def _matches_markdown_organization(value: str) -> bool:
        return (
            any(term in value for term in (".md", "markdown"))
            and any(term in value for term in ("criar", "criado", "novo"))
            and any(term in value for term in ("organizar", "organizacao"))
        )

    @staticmethod
    def _matches_job_failure(value: str) -> bool:
        return (
            "job" in value
            and any(term in value for term in ("falhar", "falha"))
            and any(term in value for term in ("avise", "avisar", "notifique"))
        )
