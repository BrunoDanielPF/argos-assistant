from datetime import date

from assistant.memory.long_term import LongTermMemoryStore
from assistant.memory.markdown_exporter import MarkdownMemoryExporter
from assistant.memory.migration import MarkdownMemoryMigrator
from assistant.memory.models import MemoryStatus
from assistant.memory.repository import MemoryRepository


def test_markdown_migration_is_idempotent_and_exportable(tmp_path):
    legacy_dir = tmp_path / "legacy"
    store = LongTermMemoryStore(legacy_dir)
    store.remember(
        "O usuario prefere respostas curtas.",
        context="preferencias",
        today=date(2026, 6, 11),
    )
    repository = MemoryRepository(tmp_path / "argos.db")
    migrator = MarkdownMemoryMigrator(repository, store)

    first = migrator.migrate()
    second = migrator.migrate()
    export_path = MarkdownMemoryExporter(repository).export(tmp_path / "export.md")

    assert first.imported == 1
    assert second.imported == 0
    assert len(repository.list(status=MemoryStatus.ACTIVE)) == 1
    assert "O usuario prefere respostas curtas." in export_path.read_text(
        encoding="utf-8"
    )


def test_markdown_migration_does_not_import_sensitive_content(tmp_path):
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    (legacy_dir / "correcoes.md").write_text(
        "# Correcoes\n\n"
        "## Credencial\n\n"
        "- Data: 2026-06-11\n"
        "- Contexto: geral\n"
        "- Aprendizado: meu token e abc123\n"
        "- Fonte: arquivo manual\n\n",
        encoding="utf-8",
    )
    repository = MemoryRepository(tmp_path / "argos.db")

    report = MarkdownMemoryMigrator(
        repository,
        LongTermMemoryStore(legacy_dir),
    ).migrate()

    assert report.imported == 0
    assert report.skipped == 1
    assert repository.list() == []
