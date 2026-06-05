# MCP Server Creation

Use this skill when adding an MCP server or MCP-backed tool for Argos.

Workflow:
- Define the tool purpose, inputs, outputs, and failure modes first.
- Keep the MCP server isolated from Argos core orchestration.
- Treat MCP tools as advisory or tool providers; local side effects still require Argos policy checks.
- Add schema validation for each tool input.
- Add tests for tool listing, tool invocation, invalid input, and failure response.

Output:
- Tool list and schemas.
- Server startup command.
- Integration point in Argos.
- Safety policy for each tool.
