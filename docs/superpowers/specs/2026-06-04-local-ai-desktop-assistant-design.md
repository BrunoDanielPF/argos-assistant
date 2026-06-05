# Local AI Desktop Assistant - MVP Design

## Objective

Build a local-first autonomous assistant for Windows that starts as a CLI application and can later evolve into a background desktop assistant with voice interaction. The MVP must:

- run with a local language model
- execute useful computer actions
- assist with technical and productivity tasks
- suggest next steps based on context
- support local skills and basic MCP compatibility
- apply confirmation policies for sensitive actions

## Product Scope

The MVP focuses on a reusable core, not on the final desktop experience. The first release is a text CLI with architecture prepared for future voice input, hotkeys, and background execution.

Included capability groups:

- System: open programs, open URLs, search files, run controlled local commands
- Productivity: draft text, explain topics, summarize content, suggest next steps
- Development: help with code, logs, Git-oriented assistance, script generation, troubleshooting

The MVP should balance system automation and technical assistance instead of specializing in only one of them.

## Architecture

The system will use a modular Python core. The CLI is only one interface layer over a reusable agent runtime.

Primary flow:

1. The user writes a request in the CLI.
2. The agent evaluates intent and available capabilities.
3. The planner decides whether the request should be answered, suggested, or executed.
4. If execution is required, the planner emits a structured action request.
5. The executor validates permissions and asks for confirmation when policy requires it.
6. The result returns to the agent, which produces a final answer and optional follow-up suggestions.

Core modules:

- `cli`: interactive shell, session loop, internal commands, confirmation prompts
- `agent_core`: orchestrates reasoning, capabilities, memory, and tool results
- `llm_adapter`: local model integration through Ollama
- `planner`: converts user intent into structured plans and action requests
- `capability_registry`: catalog of actions, skills, MCP tools, risk level, and argument schema
- `action_executor`: executes validated local actions
- `session_memory`: stores short-lived conversational and execution context
- `suggestion_engine`: proposes useful next actions after each interaction
- `skill_loader`: loads local skill definitions from disk
- `mcp_adapter`: connects to compatible MCP servers and exposes their tools to the agent

## Model Strategy

The local runtime will use Ollama on Windows with a Qwen3-family model as the initial assistant model.

Recommended baseline:

- runtime: Ollama
- default model: Qwen3 8B Instruct, quantized for local inference
- tuning track: Qwen3 4B or 8B with LoRA or QLoRA
- future specialization: optional coding-oriented variant for development tasks if the baseline model proves insufficient

Reasoning:

- the machine profile supports a useful local model for inference
- 8B is a realistic balance between quality and responsiveness
- 14B+ is likely to degrade responsiveness for an interactive assistant on this hardware
- Qwen3 aligns well with multilingual instruction following, reasoning, coding, and agent workflows

Two levels of customization are part of the design:

1. Lightweight model customization through Ollama model creation with system prompts, templates, and parameters.
2. Fine-tuning through LoRA or QLoRA on task-specific examples, using a training stack such as Unsloth.

## Skills and MCP Compatibility

The MVP will support both local skills and basic MCP integration, but in a controlled scope.

### Skills

Skills are local packages that define reusable assistant behaviors. A skill should be loadable from a folder structure such as:

- `skills/<skill-name>/skill.yaml`
- `skills/<skill-name>/prompts/...`
- `skills/<skill-name>/resources/...`

Each skill should declare:

- name and description
- trigger hints
- instructions or prompt fragments
- optional capability dependencies
- permission profile

The agent can select a skill during planning, but the skill does not directly execute machine actions.

### MCP

The MVP includes a minimal MCP adapter that can:

- register one or more MCP servers
- list available tools
- call a selected tool with structured arguments
- return tool results to the planner and agent

The initial implementation should support a small number of known-good MCP integrations rather than generic ecosystem automation.

### Safety boundary

Skills and MCP tools are advisory and tool-oriented layers. They do not bypass policy. Any action with local side effects must still pass through the common executor and confirmation logic.

## Execution and Safety Model

The assistant will support three execution classes:

1. `Auto-execute`: low-risk actions such as opening known applications or opening URLs.
2. `Confirm-before-run`: actions such as typing text, creating or editing files, running shell commands, or invoking external tools with machine impact.
3. `Blocked`: destructive or out-of-scope operations not allowed in the MVP.

Examples:

- open calculator: auto-execute
- open VS Code in a project folder: auto-execute
- type a paragraph into another application: confirm
- create or modify a file: confirm
- remove files or execute dangerous system changes: blocked in the MVP

Every execution should produce an audit event in the local session log.

## Memory and Suggestions

The MVP will use short-session memory rather than long-term autonomous memory.

Stored context:

- recent user requests
- recent plans
- recent tool and action results
- pending suggestions or follow-ups

Suggestion behavior:

- after answering a technical question, suggest a concrete next action
- after opening an app or searching files, suggest a likely continuation
- after a failure, suggest a recovery step or clarification

Suggestions must remain bounded to the current session context and must not become persistent autonomous task scheduling in the MVP.

## CLI Experience

The first interface is text-only, but the architecture must allow voice later without changing the core.

CLI requirements:

- interactive session loop
- slash-style internal commands such as `/help`, `/tools`, `/skills`, `/model`, `/history`
- explicit confirmation prompts for medium-risk actions
- visible plan summary before multi-step execution
- clear distinction between answer, proposed action, and executed action

Future voice support should be added as a new input layer that forwards normalized intents into the same agent core.

## Data Flow

Normal request flow:

1. read user input
2. build prompt from session context, skills, and available capabilities
3. query local model
4. parse structured intent or plan
5. validate against capability registry
6. confirm if policy requires it
7. execute tool or local action
8. summarize result
9. emit suggestions

Fallback behavior:

- if the model response is ambiguous, ask the user for clarification
- if a requested action cannot be mapped to a known capability, answer without execution
- if an MCP tool fails, surface the error and propose a local fallback when possible

## Non-Goals for the MVP

The following items are explicitly out of scope:

- background daemon or tray application
- always-listening voice capture
- remote cloud inference as the default path
- marketplace or auto-installation for skills
- unrestricted desktop control
- autonomous long-running task scheduling
- unrestricted destructive file or system actions

## Verification Strategy

The implementation should be validated with focused tests around the system boundaries:

- planner tests for intent-to-action decisions
- executor policy tests for allowed, confirm, and blocked actions
- skill loading tests
- MCP adapter contract tests using mock servers
- CLI smoke tests for confirmation and result rendering

Manual validation should cover:

- opening programs
- opening URLs
- handling confirmations
- responding to technical prompts
- loading a sample skill
- calling a sample MCP tool

## Initial Delivery Plan

The first implementation slice should prioritize:

1. Python CLI shell
2. Ollama adapter
3. capability registry
4. action executor for low-risk local actions
5. planner with structured action output
6. confirmation policy
7. session memory
8. sample local skill
9. sample MCP integration
10. next-step suggestions

## Open Implementation Decisions

The design intentionally leaves these as implementation choices to be resolved in the planning phase:

- precise Python CLI framework choice
- exact structured output format between planner and executor
- config file format for app settings
- concrete sample MCP server used in the MVP
- whether shell command execution is included in the first implementation slice or the second
