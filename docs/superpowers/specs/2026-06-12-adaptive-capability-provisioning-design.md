# Adaptive Capability Provisioning Design

## Goal

Convert a real unsupported capability into a reviewable local tool draft
proposal without enabling the tool, executing it, or retrying the original
action.

## Architecture

`CapabilityProvisioningService` receives the requested capability, user goal,
extracted arguments, platform context, and original action. It produces a
strict `ToolDefinition` proposal only when the request can be narrowed to a
safe local operation.

The `AssistantAgent` calls the service when registry validation returns
`unsupported_capability`. A safe proposal becomes a persisted confirmation for
the internal action `tool.provision_draft`. Approval calls the service again to
create files through the existing `ToolDraftGenerator`. Rejection creates
nothing.

## Safety

- Generic shell execution is never provisioned.
- Shell requests must map to a fixed executable and fixed operation, such as
  `git status`.
- Filesystem write permissions are empty unless a future explicitly reviewed
  template requires a narrow path.
- Network access is disabled and hosts are empty.
- Destructive commands and destructive original actions are not eligible.
- Draft generation never approves, installs, enables, or invokes the tool.
- The original unsupported action is never retried.

## Initial Templates

- `shell.run` with exactly `git status` proposes `local.git.status`.
- `windows.env.set_user` proposes `local.windows.env_set_user`.
- Other safe unsupported capabilities return the capability-gap message
  without an automatic draft definition.

## Audit

Recovery audit records the unsupported capability or capability gap.
`ToolAuditLog` records `draft_proposed`, `draft_created`, and
`draft_generation_failed` events. Session audit records the pending and final
confirmation decisions.

## Response Contract

Eligible gaps return `waiting_confirmation`, `error_code=capability_gap`, and:

`Ainda nao tenho essa capacidade. Posso criar uma tool local em draft para voce revisar?`

Approval returns the generated path and final state (`validated` or
`rejected`). It does not expose the draft as an enabled capability.
