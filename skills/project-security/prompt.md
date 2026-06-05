# Project Security

Use this skill when reviewing or changing security-sensitive Argos behavior.

Workflow:
- Identify local side effects: process launch, file read/write, shell, network, MCP, and dataset access.
- Confirm whether each action is allow, confirm, or blocked.
- Do not let skills, MCP tools, or model output bypass the executor policy.
- Treat prompt injection, unsafe paths, secrets, and destructive commands as primary risks.
- Add tests for blocked and confirmation-required behavior.

Output:
- Findings or risk list.
- Current exposure versus future drift risk.
- Required policy changes.
- Verification commands.
