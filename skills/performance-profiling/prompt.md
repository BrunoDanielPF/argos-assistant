# Performance Profiling

Use this skill when diagnosing or improving Argos performance.

Workflow:
- Measure before changing code.
- Break latency into CLI startup, planner heuristics, Ollama call, policy check, executor action, and rendering.
- Prefer lightweight instrumentation that can be removed or hidden behind config.
- Keep benchmark commands reproducible.
- Treat model latency and filesystem search latency separately.

Output:
- Baseline numbers.
- Suspected bottleneck.
- Proposed changes.
- Verification command and expected improvement.
