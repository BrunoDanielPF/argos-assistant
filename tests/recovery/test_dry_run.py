from assistant.recovery.dry_run import DryRunBuilder
from assistant.recovery.models import RecoveryRisk


def test_dry_run_describes_file_creation_without_creating_file(tmp_path):
    target = tmp_path / "notes.md"

    plan = DryRunBuilder().build(
        "create_file",
        {"path": str(target), "content": "hello"},
    )

    assert plan.action == "create_file"
    assert plan.resources_affected == [str(target)]
    assert plan.permissions_required == [f"write:{target}"]
    assert plan.risk == RecoveryRisk.MEDIUM
    assert plan.requires_confirmation is True
    assert not target.exists()


def test_dry_run_marks_delete_as_non_executable():
    plan = DryRunBuilder().build(
        "delete_files",
        {"path": ".", "pattern": "*.tmp"},
    )

    assert plan.risk == RecoveryRisk.CRITICAL
    assert plan.can_execute is False
    assert "nao sera executada automaticamente" in plan.expected_result.lower()

