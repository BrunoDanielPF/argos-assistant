from assistant.memory.session import SessionMemory


def test_session_memory_stores_and_clears_pending_clarification():
    memory = SessionMemory()
    pending = {
        "field": "write_mode",
        "question": "Substituir ou adicionar?",
        "action": {
            "capability": "write_file",
            "arguments": {"path": "notes.md"},
        },
        "options": [{"id": "replace", "label": "substituir"}],
    }

    memory.set_pending_clarification(pending)

    context = memory.snapshot()["context"]
    assert context["pending_clarification"] == pending
    assert context["active_task"] == {
        "capability": "write_file",
        "pending_field": "write_mode",
    }

    memory.clear_pending_clarification()

    context = memory.snapshot()["context"]
    assert context["pending_clarification"] is None
    assert context["active_task"] is None
