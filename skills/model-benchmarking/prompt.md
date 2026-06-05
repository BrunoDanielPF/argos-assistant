# Model Benchmarking

Use this skill when evaluating local models for Argos.

Workflow:
- Define benchmark dimensions: planning accuracy, JSON validity, latency, tool selection, answer quality, and refusal behavior.
- Use fixed prompts and fixed environment settings for comparisons.
- Record model name, quantization, hardware, timeout, and Ollama settings.
- Separate heuristic-routed commands from LLM-routed commands.
- Report failures with raw model output when useful.

Output:
- Benchmark matrix.
- Metrics and pass criteria.
- Commands to run.
- Recommendation for default model and fallback model.
