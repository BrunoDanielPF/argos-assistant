from assistant.mcp.client import MCPClient


class FakeTransport:
    def __init__(self) -> None:
        self.requests = []

    def request(self, method: str, payload: dict) -> dict:
        self.requests.append((method, payload))
        if method == "tools/list":
            return {"tools": [{"name": "search_docs"}]}
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "done"}]}
        raise AssertionError(method)


def test_mcp_client_lists_and_calls_tools():
    transport = FakeTransport()
    client = MCPClient(transport=transport)

    tools = client.list_tools()
    result = client.call_tool("search_docs", {"query": "ollama"})

    assert tools[0]["name"] == "search_docs"
    assert result["content"][0]["text"] == "done"
    assert transport.requests == [
        ("tools/list", {}),
        (
            "tools/call",
            {"name": "search_docs", "arguments": {"query": "ollama"}},
        ),
    ]
