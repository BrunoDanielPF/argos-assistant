from assistant.memory.session import SessionMemory
from assistant.models import AuditEvent, Suggestion


def test_session_memory_tracks_turns_audit_and_suggestions():
    memory = SessionMemory()
    memory.set_context(current_cwd="C:\\workspace", default_search_root="C:\\workspace")
    memory.add_user_message("open vscode")
    memory.add_assistant_message("Opening VS Code")
    memory.add_audit_event(AuditEvent(kind="action", message="opened vscode"))
    memory.set_suggestions([Suggestion(text="Open the project folder next")])

    snapshot = memory.snapshot()

    assert snapshot["history"][0]["role"] == "user"
    assert snapshot["history"][1]["role"] == "assistant"
    assert snapshot["audit"][0]["message"] == "opened vscode"
    assert snapshot["suggestions"][0]["text"] == "Open the project folder next"
    assert snapshot["context"]["current_cwd"] == "C:\\workspace"
    assert snapshot["context"]["default_search_root"] == "C:\\workspace"


def test_session_memory_isolated_from_caller_mutation():
    memory = SessionMemory()
    event = AuditEvent(kind="action", message="opened vscode")
    suggestions = [Suggestion(text="Open the project folder next")]

    memory.add_audit_event(event)
    memory.set_suggestions(suggestions)

    event.message = "mutated after write"
    suggestions[0].text = "mutated after write"

    snapshot = memory.snapshot()

    assert snapshot["audit"][0]["message"] == "opened vscode"
    assert snapshot["suggestions"][0]["text"] == "Open the project folder next"


def test_session_memory_updates_context_fields():
    memory = SessionMemory()

    memory.set_context(current_cwd="C:\\one")
    memory.set_context(default_search_root="C:\\two")

    snapshot = memory.snapshot()

    assert snapshot["context"] == {
        "session_id": None,
        "current_cwd": "C:\\one",
        "default_search_root": "C:\\two",
        "user_home": None,
        "last_search_results": [],
        "pending_clarification": None,
        "active_task": None,
    }


def test_session_memory_tracks_last_search_results():
    memory = SessionMemory()

    memory.set_last_search_results(["C:\\one\\README.md", "C:\\one\\notes.txt"])

    snapshot = memory.snapshot()

    assert snapshot["context"]["last_search_results"] == [
        "C:\\one\\README.md",
        "C:\\one\\notes.txt",
    ]
