from assistant.memory.session import SessionMemory


def test_session_memory_stores_and_clears_pending_clarification():
    memory = SessionMemory()
    pending = {
        "field": "write_mode",
        "question": "Substituir ou adicionar?",
        "options": [{"id": "replace", "label": "substituir"}],
    }

    memory.set_pending_clarification(pending)

    assert memory.snapshot()["context"]["pending_clarification"] == pending

    memory.clear_pending_clarification()

    assert memory.snapshot()["context"]["pending_clarification"] is None
