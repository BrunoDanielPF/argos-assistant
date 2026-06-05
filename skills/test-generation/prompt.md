# Test Generation

Use this skill when adding or improving tests for Argos.

Workflow:
- Start with the behavior the user needs, not implementation details.
- Prefer small pytest tests around one behavior.
- Mock Ollama and external processes unless the task is a smoke test.
- Cover success, failure, and policy behavior for actions.
- For CLI behavior, use Typer CliRunner.

Output:
- Test cases grouped by module.
- Expected failing test first when changing behavior.
- Verification command, usually `python -m pytest -q`.
