# CLI Command Generation

Use this skill when adding CLI commands or interactive slash commands to Argos.

Workflow:
- Decide whether the feature belongs in a Typer command or interactive slash command.
- Keep one-shot commands and interactive behavior consistent.
- Add clear help text and predictable output.
- Route actions through the agent unless the command is purely session management.
- Add CliRunner tests.

Output:
- Command name and arguments.
- Example usage.
- Policy and confirmation behavior.
- Tests and smoke command.
