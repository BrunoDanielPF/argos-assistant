# Argos ADW Acceptance Tests and Documentation Design

## Scope

This delivery makes the requested ADW acceptance criteria explicit, adds
defense-in-depth redaction for workflow logs, and publishes user-facing ADW
documentation.

## Acceptance Suite

`tests/workflows/test_adw_acceptance.py` maps one test to each requested
criterion:

- PDF template shape and lifecycle defaults;
- validator failures;
- lifecycle guards;
- sequential runner behavior and persistence;
- secret redaction;
- CLI generate, inspect, and noop run.

Existing lower-level tests remain in place. The acceptance file documents the
feature contract without replacing focused unit tests.

## Log Redaction

`assistant.workflows.redaction` recursively sanitizes dictionaries, lists, and
tuples. Keys are normalized by removing punctuation and comparing case
insensitively.

The following key families are redacted:

```text
secret
token
password
api_key
private_key
```

Values are replaced with `[REDACTED]`.

Redaction occurs:

1. before trigger events, step inputs, and step outputs are persisted;
2. again before the CLI renders workflow logs.

This prevents newly generated logs from storing sensitive values and protects
display if older or externally inserted records contain them.

## Documentation

`docs/WORKFLOWS.md` explains:

- what Argos Adaptative Dynamic Workflows are;
- why workflows are declarative;
- why model-generated free-form scripts are not executed;
- lifecycle and policy flow;
- all workflow CLI commands;
- a complete PDF example;
- validation, confirmation, blocking, budgeting, and audit rules.

The README links to the dedicated guide without duplicating it.

