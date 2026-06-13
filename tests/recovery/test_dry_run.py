from assistant.recovery.dry_run import DryRunBuilder
from assistant.recovery.models import RecoveryRisk


def test_dry_run_describes_file_creation_without_creating_file(tmp_path):
    target = tmp_path / "notes.md"

    plan = DryRunBuilder().build(
        "create_file",
        {"path": str(target), "content": "hello"},
    )

    assert plan.action == "file.create"
    assert plan.resources_affected == [str(target)]
    assert plan.permissions_required == [f"write:{target}"]
    assert plan.risk == RecoveryRisk.MEDIUM
    assert plan.requires_confirmation is True
    assert not target.exists()


def test_delete_dry_run_is_read_only_and_executable():
    plan = DryRunBuilder().build(
        "delete_files",
        {"path": ".", "pattern": "*.tmp"},
    )

    assert plan.action == "file.delete_dry_run"
    assert plan.risk == RecoveryRisk.LOW
    assert plan.can_execute is True
    assert plan.requires_confirmation is False
    assert "simulacao" in plan.expected_result.lower()
    assert "nenhum arquivo" in plan.expected_result.lower()


def test_real_delete_dry_run_explains_affected_resource_and_confirmation(
    tmp_path,
):
    target = tmp_path / "lixo.tmp"
    target.write_text("keep", encoding="utf-8")

    plan = DryRunBuilder().build(
        "file.delete_one",
        {"path": str(target), "recursive": False},
    )

    assert plan.can_execute is True
    assert plan.requires_confirmation is True
    assert plan.resources_affected == [str(target)]
    assert "excluiria" in plan.expected_result.lower()
    assert target.exists()
