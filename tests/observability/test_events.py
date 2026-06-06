import json

import pytest

from assistant.observability.events import EventLog, SensitiveEventData


def test_event_log_does_not_persist_prompt(tmp_path):
    path = tmp_path / "events.jsonl"
    log = EventLog(path)

    log.write("request_finished", "s1", "r1", {"duration_ms": 12})

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["kind"] == "request_finished"
    assert payload["details"] == {"duration_ms": 12}
    assert "prompt" not in path.read_text(encoding="utf-8")


def test_event_log_rejects_nested_sensitive_keys(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")

    with pytest.raises(SensitiveEventData):
        log.write(
            "request_failed",
            "s1",
            "r1",
            {"error": {"token": "secret"}},
        )
