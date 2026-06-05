# Internal Prompt Creation

Use this skill when creating or revising prompts used inside Argos.

Workflow:
- Define the target component: planner, persona, skill routing, command simulation, or dataset generation.
- Require structured JSON when the output feeds code.
- Include supported capabilities and forbid unsupported actions.
- Add examples only when they reduce model ambiguity.
- Keep prompts short enough to be maintainable.

Output:
- Prompt text.
- Expected input and output schema.
- Failure cases the prompt must avoid.
- Tests or manual examples for validation.
