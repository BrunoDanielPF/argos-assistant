class MCPClient:
    def __init__(self, transport) -> None:
        self._transport = transport

    def list_tools(self) -> list[dict]:
        response = self._transport.request("tools/list", {})
        return response["tools"]

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self._transport.request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
