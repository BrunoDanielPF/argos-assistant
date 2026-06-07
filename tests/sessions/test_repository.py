from assistant.memory.session import SessionMemory
from assistant.models import AuditEvent, Suggestion
from assistant.sessions.repository import SessionRepository


def test_session_survives_repository_reopen(tmp_path):
    database = tmp_path / "argos.db"
    first = SessionRepository(database)
    memory = SessionMemory()
    memory.add_user_message("conte ate dez")
    memory.add_assistant_message("vamos comecar")
    memory.add_audit_event(AuditEvent(kind="answer", message="vamos comecar"))
    memory.set_suggestions([Suggestion(text="continue")])
    memory.set_context(current_cwd="C:\\workspace", user_home="C:\\Users\\user")
    first.save("default", memory.snapshot())
    first.close()

    second = SessionRepository(database)
    restored = second.load("default")

    assert restored is not None
    assert restored["history"][0]["content"] == "conte ate dez"
    assert restored["audit"][0]["kind"] == "answer"
    assert restored["suggestions"][0]["text"] == "continue"
    assert restored["context"]["current_cwd"] == "C:\\workspace"
    second.close()


def test_session_memory_restores_snapshot_without_sharing_mutations():
    source = SessionMemory()
    source.add_user_message("original")
    source.set_last_search_results(["C:\\a.md"])
    snapshot = source.snapshot()

    restored = SessionMemory.from_snapshot(snapshot)
    snapshot["history"][0]["content"] = "changed"
    snapshot["context"]["last_search_results"].append("C:\\b.md")

    restored_snapshot = restored.snapshot()
    assert restored_snapshot["history"][0]["content"] == "original"
    assert restored_snapshot["context"]["last_search_results"] == ["C:\\a.md"]


def test_repository_returns_none_for_unknown_session(tmp_path):
    repository = SessionRepository(tmp_path / "argos.db")

    assert repository.load("missing") is None
    repository.close()


def test_repository_persists_and_resolves_confirmation_once(tmp_path):
    repository = SessionRepository(tmp_path / "argos.db")
    repository.save_confirmation(
        confirmation_id="confirm-1",
        session_id="default",
        run_id="run-1",
        capability="write_file",
        arguments={"path": "C:\\Users\\user\\receita.md", "content": "receita"},
    )

    pending = repository.load_confirmation("confirm-1")
    resolved = repository.resolve_confirmation("confirm-1", approved=True)
    duplicate = repository.resolve_confirmation("confirm-1", approved=False)

    assert pending["status"] == "pending"
    assert pending["arguments"]["content"] == "receita"
    assert resolved["status"] == "approved"
    assert duplicate is None
    repository.close()
