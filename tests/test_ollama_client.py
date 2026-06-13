from assistant.llm.ollama_client import OllamaClient


def test_ollama_client_sends_runtime_options(monkeypatch):
    recorded = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"message": {"content": '{"mode":"answer","content":"ok"}'}}

    def fake_post(url, json, timeout):
        recorded["url"] = url
        recorded["json"] = json
        recorded["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("assistant.llm.ollama_client.httpx.post", fake_post)

    client = OllamaClient(
        model="argos-qwen3:4b",
        base_url="http://localhost:11434/api",
        timeout_seconds=12.0,
        keep_alive="10m",
        think=False,
        options={"num_predict": 512, "num_ctx": 4096},
    )

    response = client.chat([{"role": "user", "content": "oi"}])

    assert response["response"] == '{"mode":"answer","content":"ok"}'
    assert recorded["url"] == "http://localhost:11434/api/chat"
    assert recorded["timeout"] == 12.0
    assert recorded["json"]["model"] == "argos-qwen3:4b"
    assert recorded["json"]["stream"] is False
    assert recorded["json"]["format"] == "json"
    assert recorded["json"]["think"] is False
    assert recorded["json"]["keep_alive"] == "10m"
    assert recorded["json"]["options"] == {"num_predict": 512, "num_ctx": 4096}


def test_ollama_client_sends_json_schema_for_structured_output(monkeypatch):
    recorded = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"message": {"content": '{"name":"file.metadata.stat"}'}}

    def fake_post(url, json, timeout):
        recorded["json"] = json
        return FakeResponse()

    monkeypatch.setattr("assistant.llm.ollama_client.httpx.post", fake_post)
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    client = OllamaClient(model="argos-qwen3:4b")

    response = client.chat_structured(
        [{"role": "user", "content": "proponha uma tool"}],
        schema,
    )

    assert response["response"] == '{"name":"file.metadata.stat"}'
    assert recorded["json"]["format"] == schema
