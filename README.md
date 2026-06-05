# Argos

Argos is a local-first Windows assistant MVP built in Python with Ollama.

## Requirements

- Python 3.12
- Ollama running locally
- A local model such as `qwen3:8b`

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
ollama pull qwen3:8b
```

## Usage

```bash
argos
argos chat "open ollama website"
argos chat "summarize what an MCP server is"
```

Use `argos` para conversa continua no terminal. Use `argos chat "..."` para uma unica solicitacao.
`assistant` continua disponivel como alias de compatibilidade.

## How To Use `argos chat`

The CLI sends your prompt to the local model through Ollama, converts the model output into either:

- a direct answer
- an executable action such as opening a URL or searching files

Basic examples:

```bash
argos
argos chat "open ollama website"
argos chat "summarize what an MCP server is"
argos chat "find notes.txt in C:\\Users\\frand\\Documents"
argos interactive
```

Expected behavior:

- if the model returns an action, the assistant executes the supported capability and prints the result
- if the model returns an answer, the assistant prints the answer text
- action results are printed with `OK` or `ERROR` status
- after each response, the assistant prints one or more next-step suggestions

Sensitive capabilities such as file search require confirmation before execution. The CLI shows the capability name and arguments, then asks whether the action should continue.

## Project Skills

Argos loads local skill metadata from `skills/<skill-name>/skill.yaml`. Each project skill also includes a `prompt.md` with operational guidance.

Initial project-management skills:

- `project-architecture`
- `mcp-server-creation`
- `test-generation`
- `internal-prompt-creation`
- `dataset-generation`
- `dataset-curation`
- `model-benchmarking`
- `performance-profiling`
- `configuration-management`
- `local-setup`
- `cli-command-generation`
- `project-security`
- `command-simulation`

These skills are advisory in this phase. They guide planning and generation, but they do not execute local actions or bypass executor policy.

## How To Test

### 1. Run the automated tests

```bash
python -m pytest -q
```

Expected result:

- all tests pass

### 2. Confirm the CLI is installed

```bash
argos --help
```

Expected result:

- the help output lists the `chat` command

### 3. Confirm the Ollama runtime is available

If the `ollama` command is available:

```bash
ollama list
ollama pull qwen3:8b
```

If the Ollama daemon is already listening on `http://localhost:11434` but the CLI is not on `PATH`, you can pull the model through the local API:

```powershell
$body = @{ name = 'qwen3:8b'; stream = $false } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:11434/api/pull' -Method Post -ContentType 'application/json' -Body $body
```

### 4. Run a manual smoke test

```bash
argos chat "open ollama website"
```

Expected result:

- the assistant returns a success message
- the browser opens `https://ollama.com`
- at least one suggestion is printed below the main result

### 5. Run an interactive smoke test

```bash
argos
```

Example session:

```text
argos: open ollama website
[OK] Opened https://ollama.com
- Ask me to open documentation next
argos: exit
Bye.
```

`argos interactive` continua disponivel e tem o mesmo comportamento. O comando simples `argos` agora entra nesse modo por padrao.

## Troubleshooting

- `ollama` not recognized:
  the Ollama CLI is not installed or not on `PATH`
- `ConnectError` or connection refused:
  the Ollama daemon is not running on `localhost:11434`
- `{"models":[]}` from `/api/tags`:
  the daemon is up, but no model has been pulled yet
- planner/action mismatch from the local model:
  rerun after updating to the latest project code, which now normalizes both `capability/arguments` and `action/<fields>` action formats
