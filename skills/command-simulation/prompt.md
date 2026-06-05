# Command Simulation

Use this skill when previewing what Argos would do before execution.

Workflow:
- Parse the user request into the likely plan.
- Show capability, arguments, policy class, and expected side effects.
- Do not execute local actions during simulation.
- Flag ambiguous or unsupported commands.
- Include what confirmation prompt would appear for confirm-required actions.

Output:
- Simulated plan.
- Policy decision.
- Expected result if executed.
- Risks or ambiguity.
