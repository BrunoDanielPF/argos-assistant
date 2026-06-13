# Capability Provisioning Lifecycle Design

## Goal

Complete the safe lifecycle from a capability gap to an enabled local tool
and an explicitly confirmed retry of the original action.

## Lifecycle

1. The unsupported action produces a safe draft proposal.
2. The first confirmation creates a validated draft.
3. The response offers a second confirmation to approve, install, and enable
   that exact draft.
4. Approval transitions the tool through `approved`, `installed`, and
   `enabled`.
5. The gateway evicts the cached agent for that session and rebuilds it from
   persisted memory, producing a fresh catalog, capability registry, planner,
   executor, and tool runner.
6. The original action is translated to the enabled tool name and returned as
   a third confirmation with permission summary and dry-run.
7. Only the third approval executes the tool.

## Boundaries

- Approval, installation, and enablement are one explicit user-approved
  lifecycle operation.
- The original unsupported action is never executed before registry reload.
- Registry reload affects only the current session.
- The lifecycle does not mutate registry objects in place.
- The Windows environment e2e test uses a fake runner and never writes the
  actual Windows registry.
- Rejected lifecycle or retry confirmations do not execute or enable anything.

## Persistence

The provisioning confirmation payload carries the generated draft path,
definition, and original action. The lifecycle confirmation carries the same
original action so gateway restart or agent eviction does not lose retry
context.

## Audit

Tool audit records:

- `draft_created`
- `tool_approved`
- `tool_installed`
- `tool_enabled`
- `registry_reloaded`
- `retry_confirmation_required`
- runner `execution_started` and `execution_finished`

Recovery audit continues recording the initial `capability_gap`.
