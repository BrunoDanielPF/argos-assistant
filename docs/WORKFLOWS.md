# Argos Adaptative Dynamic Workflows

## O que é ADW

Argos Adaptative Dynamic Workflows, ou ADW, é a camada de automações locais,
declarativas e auditáveis do Argos.

O usuário descreve uma intenção em linguagem natural:

```text
quando eu baixar um PDF, sugira mover para a pasta correta
```

O planner heurístico seleciona um template conhecido e cria um workflow
estruturado. Esse workflow nasce como `draft`: ele não é habilitado e não
executa nenhuma ação durante a geração.

A regra de responsabilidade é:

```text
LLM ou heurística sugere.
Runtime estrutura.
Validator valida.
Policy autoriza.
Approval confirma.
Runner executa.
Audit registra.
```

O núcleo ADW não depende do Ollama nem de um modelo específico.

## Por que o workflow é declarativo

Um workflow declarativo descreve:

- o trigger;
- a estratégia de execução;
- os steps e handlers permitidos;
- os argumentos de cada step;
- a policy;
- o budget;
- o escopo;
- os metadados de auditoria.

Essa estrutura permite que o Argos valide o workflow antes da execução,
compare cada ação com uma policy determinística e registre cada run e step no
SQLite.

JSON e YAML também tornam o workflow legível, exportável e revisável sem
depender do modelo que ajudou a criá-lo.

## Por que o Argos não executa script livre

Código livre gerado por modelo pode conter operações destrutivas, comandos
ofuscados, acesso a dados sensíveis ou efeitos que não aparecem claramente na
solicitação original.

Por isso, o ADW não executa Python, PowerShell, shell ou outro script arbitrário
produzido pelo modelo.

Cada step referencia um handler conhecido, como:

```text
noop
notification.send
files.inspect
files.suggest_destination
workflow.ask_confirmation
files.move
files.write
shell.run
```

Um handler desconhecido falha na validação. `shell.run` possui policy
restritiva e não faz parte do registry local usado pela CLI nesta versão.

## Lifecycle

O fluxo normal é:

```text
draft -> validated -> approved -> enabled
```

| Status | Significado |
|---|---|
| `draft` | Workflow criado, ainda sem autorização. |
| `validated` | Estrutura, handlers, policy e budget foram validados. |
| `approved` | O usuário aprovou o contrato declarativo. |
| `enabled` | O workflow pode criar runs. |
| `disabled` | Workflow temporariamente desabilitado. |
| `rejected` | Workflow rejeitado e não habilitável. |
| `archived` | Workflow removido do uso ativo sem exclusão física. |

As transições são verificadas pelo runtime. Por exemplo:

- `draft` não pode ir diretamente para `enabled`;
- somente `validated` pode ir para `approved`;
- somente `approved` pode ir para `enabled`;
- `rejected` não pode ser habilitado.

## Comandos CLI

```bash
argos workflows list
argos workflows generate "<descrição>"
argos workflows inspect <id>
argos workflows validate <id>
argos workflows approve <id>
argos workflows reject <id>
argos workflows enable <id>
argos workflows disable <id>
argos workflows run <id>
argos workflows logs <id>
argos workflows delete <id>
argos workflows export <id>
```

IDs completos ou prefixos únicos com pelo menos oito caracteres são aceitos.

Fluxo básico:

```bash
argos workflows generate "todo dia às 9h, revise minhas tarefas"
argos workflows inspect <id>
argos workflows validate <id>
argos workflows approve <id>
argos workflows enable <id>
argos workflows run <id>
argos workflows logs <id>
```

`delete` arquiva o workflow. Ele não remove fisicamente o registro.

## Exemplo: organização de PDF

Comando:

```bash
argos workflows generate "quando eu baixar um PDF, sugira mover para a pasta correta"
```

Contrato simplificado exportado em YAML:

```yaml
schema_version: "1.0"
name: Organizar PDFs baixados
status: draft
trigger:
  type: file_created
  arguments:
    path: ~/Downloads
    pattern: "*.pdf"
strategy: sequential
steps:
  - id: inspect_pdf
    uses: files.inspect
    with_args:
      path: "${trigger.path}"
  - id: suggest_destination
    uses: files.suggest_destination
    with_args:
      path: "${trigger.path}"
  - id: confirm_move
    uses: workflow.ask_confirmation
    requires_confirmation: true
  - id: move_pdf
    uses: files.move
    with_args:
      source: "${trigger.path}"
      destination: "${steps.suggest_destination.output.destination}"
    requires_confirmation: true
policy:
  default_decision: blocked
  actions:
    files.inspect: allow
    files.suggest_destination: allow
    workflow.ask_confirmation: confirm
    files.move: confirm
budget:
  max_steps: 4
  max_runtime_seconds: 120
  max_model_calls: 0
  max_parallel_tasks: 1
```

O workflow é apenas criado. Para executá-lo, ainda são necessárias validação,
aprovação e habilitação.

## Regras de segurança

### Draft obrigatório

Todo workflow gerado por linguagem natural nasce como `draft`.

### Budget obrigatório

Todo workflow deve limitar:

- quantidade de steps;
- duração máxima;
- chamadas de modelo;
- paralelismo.

`max_steps` não pode ser menor que a quantidade declarada de steps.

### Policy determinística

Decisões disponíveis:

```text
allow
confirm
blocked
```

Regras mínimas:

| Ação | Decisão mínima |
|---|---|
| `notification.send` | `allow` |
| `files.inspect` | `allow` |
| `files.suggest_destination` | `allow` |
| `files.move` | `confirm` |
| `files.write` | `confirm` |
| `shell.run` | `confirm` ou `blocked` |
| `workflow.enable` | `confirm` |
| ação destrutiva | `blocked` |

A policy declarada pode tornar uma ação mais restritiva, mas não pode reduzir o
nível mínimo definido pelo runtime.

### Comandos destrutivos

O validator e o policy evaluator bloqueiam padrões como:

```text
rm -rf
del /s
rmdir /s
format
shutdown
curl ... | bash
Invoke-WebRequest ... | iex
powershell ... iex
```

### Confirmação

Uma ação `confirm` só é executada após aprovação. Sem um mecanismo de aprovação,
o run fica em `waiting_approval`. Uma ação `blocked` nunca chama o handler.

### Auditoria

Cada execução cria:

- um `WorkflowRun`;
- um `WorkflowRunStep` por step tentado;
- status, timestamps, inputs, outputs e erros seguros.

Os logs mascaram valores associados a:

```text
secret
token
password
api_key
private_key
```

O valor persistido ou exibido é substituído por `[REDACTED]`.

## Limites atuais

- `file_created`, `schedule` e `job_failed` já existem como contratos
  declarativos;
- a ligação residente desses triggers com polling, scheduler e eventos de jobs
  será feita em uma integração posterior;
- a estratégia disponível no MVP é `sequential`;
- a CLI local não registra `shell.run`;
- templates desconhecidos são rejeitados em vez de gerar automações parciais.
