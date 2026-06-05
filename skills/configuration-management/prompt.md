# Configuration Management

Use this skill when adding or changing Argos configuration.

Workflow:
- Prefer explicit AppConfig fields with clear defaults.
- Support environment overrides only when they are useful for local setup or automation.
- Keep secrets out of tracked files.
- Document any new config in README.
- Add tests for defaults and overrides when behavior changes.

Output:
- Config keys.
- Defaults and environment variable names.
- Files changed.
- Validation command.
