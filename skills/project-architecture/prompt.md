# Project Architecture

Use this skill when designing or changing Argos architecture.

Workflow:
- Identify the current module boundary before proposing changes.
- Keep CLI, agent, planner, executor, memory, skills, and MCP integration as separate concerns.
- Route all local side effects through the action executor and policy layer.
- Prefer incremental changes that preserve the current CLI behavior.
- State tradeoffs, risks, and tests needed for the change.

Output:
- Proposed module changes.
- Data flow from user input to model, plan, policy, executor, and response.
- Files likely to change.
- Validation commands.
