# Argos

Argos e um assistente pessoal local para Windows, construido em Python e integrado ao Ollama.

O objetivo do projeto e evoluir de uma CLI inteligente para um assistente assincrono residente no computador, capaz de ser acionado por voz, responder por voz, configurar ferramentas locais e executar tarefas na maquina pessoal com controle de seguranca.

## Contexto

Argos nasce como um assistente offline-first. A primeira versao roda no terminal, usa um modelo local leve via Ollama e ja possui uma base modular para planejar comandos, aplicar politica de permissao e executar acoes locais.

A direcao do produto e transformar esse nucleo em um assistente de computador:

- acionamento por CLI hoje e por voz/hotkey no roadmap
- resposta por texto hoje e por voz no roadmap
- uso local e offline sempre que o modelo e as ferramentas estiverem disponiveis na maquina
- preferencia por modelos menores e mais eficientes para resposta rapida no computador pessoal
- inteligencia para configurar tools, skills e MCPs
- capacidade de chamar programas, abrir arquivos, pesquisar arquivos e operar ferramentas locais
- memoria progressiva para aprender preferencias, correcoes e procedimentos recorrentes
- execucao controlada por politica de seguranca antes de qualquer efeito colateral relevante

## Estado atual

O MVP atual entrega:

- comando principal `argos`
- modo one-shot com `argos chat "..."`
- modo interativo no terminal
- integracao com Ollama usando modelo local
- abertura de URLs
- abertura de aplicativos conhecidos
- abertura de arquivos
- criacao segura de arquivos com confirmacao
- busca de arquivos com confirmacao
- abertura de resultado por indice no modo interativo
- memoria curta de sessao
- primeira versao de memoria persistente em Markdown
- recuperacao de memorias persistentes relevantes antes do planejamento
- catalogo local de capabilities
- planos multi-etapa simples para criar arquivo e abrir em seguida
- politicas `allow`, `confirm` e `blocked`
- loader de skills locais
- adaptador MCP minimo
- catalogo inicial de skills do projeto

## Estrategia de modelo

O padrao do Argos deve priorizar eficiencia, baixa latencia e uso local confortavel. Por isso, o modelo operacional padrao e um modelo customizado no Ollama, atualmente `argos-qwen3:4b`, criado em cima de `qwen3:4b`.

Diretrizes:

- usar modelo pequeno para comandos, planejamento simples, CLI e automacao local
- manter persona e regras estaveis no `Modelfile`
- reservar modelos maiores para tarefas mais complexas, benchmark ou fallback configuravel
- manter o modelo configuravel para permitir troca conforme hardware e qualidade desejada
- medir qualidade por planejamento correto, JSON valido, latencia e consumo de recursos

Modelo recomendado para o MVP:

- padrao: `argos-qwen3:4b`
- base do modelo customizado: `qwen3:4b`
- alternativa mais forte: `qwen3:8b`

Opcoes de runtime usadas pelo Argos:

- `keep_alive`: `10m`, para manter o modelo carregado depois da primeira chamada
- `format`: `json`, para reduzir respostas fora do schema esperado
- `think`: `false`, para evitar custo extra de raciocinio em comandos curtos
- `num_predict`: `512`, para limitar respostas longas sem truncar JSON estruturado
- `num_ctx`: `4096`, para manter contexto suficiente sem custo excessivo

Camadas de customizacao:

- `Modelfile`: persona, idioma, formato JSON, parametros e regras estaveis
- memoria Markdown: preferencias, correcoes e aprendizados que mudam com o tempo
- LoRA/QLoRA futuro: padroes estaveis de tool-use, planejamento e estilo apos coleta de dataset

## Memoria progressiva

Argos deve evoluir para ter memoria de longo prazo semelhante a outros assistentes modernos. Quando o usuario corrigir uma resposta, ensinar uma preferencia ou definir um procedimento recorrente, o Argos deve propor salvar esse aprendizado.

Modelo de memoria planejado:

- memoria curta: contexto da sessao atual
- memoria longa: arquivos Markdown semanticos na pasta do usuario
- pasta sugerida: `%USERPROFILE%\.argos\memory`
- arquivos por tema, como `preferencias.md`, `projetos.md`, `ferramentas.md`, `comandos.md` e `correcoes.md`

Regras:

- nunca salvar segredos, tokens, senhas ou dados sensiveis
- pedir confirmacao antes de persistir memoria
- registrar aprendizados pequenos, objetivos e verificaveis
- recuperar memorias relevantes semanticamente antes de planejar respostas ou acoes
- manter o usuario capaz de ler, editar e apagar as memorias manualmente

Implementacao atual:

- comando interativo `/remember <aprendizado>`
- atalhos em linguagem natural: `lembre que ...`, `aprenda que ...` e `corrigindo: ...`
- confirmacao antes de salvar
- escrita em `%USERPROFILE%\.argos\memory\correcoes.md`
- bloqueio simples para conteudo sensivel como senha, token, secret ou chave privada
- comando `/memory` para listar memorias persistentes
- busca lexical simples para injetar memorias relevantes no contexto do planner

## Orquestracao de workflows

Argos deve manter o core atual simples enquanto o produto ainda esta focado em CLI, tools locais e memoria. A integracao com LangGraph deve entrar de forma incremental quando o projeto chegar em tarefas assincronas, modo residente, checkpoints, retomada de execucao e human-in-the-loop.

Decisao atual:

- nao reescrever o nucleo em LangChain agora
- manter planner, policy, executor e memoria com fronteiras proprias
- avaliar LangGraph como orquestrador para o modo residente
- usar LangChain somente quando uma integracao concreta justificar a dependencia

Fluxo futuro esperado:

```text
entrada CLI/voz/hotkey
-> carregar contexto e memoria
-> planejar
-> aplicar policy
-> pausar para confirmacao quando necessario
-> executar tool
-> salvar resultado ou aprendizado
-> responder por texto/voz
```

## Roadmap

### Fase 1: CLI operacional

- melhorar comandos interativos como `/help`, `/skills`, `/tools`, `/model` e `/history`
- exibir resultados de busca com indices mais claros
- adicionar simulacao de comandos antes da execucao
- melhorar sugestoes contextuais
- integrar skills no prompt do planner
- melhorar consulta da memoria persistente com ranking semantico

### Fase 2: Tools e automacao local

- expandir `open_application` com catalogo configuravel de programas
- adicionar execucao controlada de comandos shell
- criar configuracao local para tools, paths e aliases
- permitir que Argos configure ferramentas pessoais com validacao
- melhorar suporte a MCP servers locais
- criar escrita controlada de memoria em Markdown

### Fase 3: Voz e assistente residente

- avaliar introducao incremental de LangGraph para workflows duraveis
- adicionar entrada por voz com STT local
- adicionar resposta por voz com TTS local
- criar acionamento por hotkey ou wake command
- rodar Argos em segundo plano
- manter estado entre sessoes
- permitir tarefas assincronas com fila, logs e notificacoes
- usar memoria persistente para personalizar respostas e acoes

### Fase 4: Inteligencia, avaliacao e tuning

- gerar datasets de comandos, planos e respostas
- criar curadoria de dataset
- comparar modelos locais por benchmark
- medir latencia e uso de recursos
- preparar LoRA/QLoRA para especializacao futura
- avaliar recuperacao semantica da memoria persistente

## Requisitos

- Python 3.12
- Ollama rodando localmente
- modelo base `qwen3:4b`
- modelo customizado `argos-qwen3:4b`

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
ollama pull qwen3:4b
ollama create argos-qwen3:4b -f models/argos-qwen3-4b.Modelfile
```

## Uso

Use `argos` para conversa continua no terminal:

```bash
argos
```

Exemplos no modo interativo:

```text
argos: oi
argos: open calculator
argos: vamos criar um markdown na pasta do meu usuario, esse arquivo markdown precisa ter hello world escrito
argos: find README.md
argos: /open 1
argos: exit
```

Use `argos chat "..."` para uma unica solicitacao:

```bash
argos chat "open ollama website"
argos chat "summarize what an MCP server is"
argos chat "find README.md"
```

O comando `assistant` ainda existe como alias de compatibilidade, mas o nome oficial do projeto e `argos`.

Durante chamadas ao modelo, a CLI mostra `Argos esta pensando...` enquanto aguarda a resposta.

## Comandos interativos

- `/cwd <path>`: atualiza o diretorio de contexto da sessao
- `/pwd`: mostra o diretorio atual da sessao
- `/context`: mostra o contexto atual da sessao
- `/history`: mostra o historico da sessao
- `/open <path>`: abre um arquivo pelo caminho
- `/open <indice>`: abre um item da ultima busca por indice
- `/remember <aprendizado>`: salva um aprendizado confirmado na memoria persistente
- `/memory`: lista memorias persistentes salvas
- `exit` ou `quit`: encerra a sessao

## Skills do projeto

Argos carrega metadados de skills locais em `skills/<skill-name>/skill.yaml`. Cada skill tambem possui um `prompt.md` com orientacao operacional.

Skills iniciais:

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
- `documentation-maintenance`
- `long-term-memory`
- `workflow-orchestration`

Nesta fase, as skills sao consultivas. Elas orientam planejamento, documentacao e geracao de artefatos, mas nao executam acoes locais nem ignoram a politica do executor.

## Seguranca

Argos separa raciocinio de execucao. O modelo local e o planner podem propor acoes, mas efeitos colaterais passam pelo executor e pela politica de permissao.

Classes de politica:

- `allow`: acoes simples, como abrir URL, aplicativo conhecido ou arquivo
- `confirm`: acoes sensiveis, como criar arquivo, busca de arquivos ou futuras operacoes shell
- `blocked`: acoes destrutivas ou nao suportadas

Skills, MCPs e prompts internos nao devem executar diretamente acoes na maquina. Qualquer acao local deve passar pelo mesmo fluxo de politica e confirmacao.

## Testes

Rode a suite automatizada:

```bash
python -m pytest -q
```

Verifique a CLI:

```bash
argos --help
```

Smoke test manual:

```bash
argos chat "open ollama website"
```

Teste manual de criacao segura de arquivo:

```bash
argos
```

No modo interativo:

```text
argos: vamos criar um markdown na pasta do meu usuario, esse arquivo markdown precisa ter hello world escrito
Execute this action? [y/N]: y
argos: exit
```

O arquivo esperado e:

```powershell
Get-Content "$env:USERPROFILE\hello_world.md"
```

Teste manual de memoria:

```bash
argos
```

No modo interativo:

```text
argos: lembre que eu prefiro respostas objetivas em portugues
Save this memory? [y/N]: y
argos: /memory
argos: exit
```

Depois confira o arquivo:

```powershell
Get-Content "$env:USERPROFILE\.argos\memory\correcoes.md"
```

Depois de salvar uma memoria, prompts futuros usam memorias relevantes como contexto do planner. Exemplo:

```text
argos: como voce deve responder para mim?
```

## Ollama

Se o comando `ollama` estiver disponivel:

```bash
ollama list
ollama pull qwen3:4b
ollama create argos-qwen3:4b -f models/argos-qwen3-4b.Modelfile
```

Se o daemon estiver ativo em `http://localhost:11434`, mas o comando `ollama` nao estiver no `PATH`, o modelo pode ser baixado pela API local:

```powershell
$body = @{ name = 'qwen3:4b'; stream = $false } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:11434/api/pull' -Method Post -ContentType 'application/json' -Body $body
```

Depois crie o modelo customizado usando o `Modelfile` versionado:

```powershell
$system = @'
Voce e Argos, um assistente pessoal local offline-first para Windows.
Responda em portugues por padrao.
Seja objetivo, pratico e direto.
Use memorias persistentes fornecidas no contexto como preferencias do usuario.
Quando a solicitacao exigir uma acao local suportada, Retorne JSON valido no formato:
{"mode":"action","capability":"<name>","arguments":{...}}
Quando a solicitacao for uma pergunta ou explicacao, Retorne JSON valido no formato:
{"mode":"answer","content":"<texto>"}
Quando a solicitacao precisar de varias acoes em sequencia, Retorne JSON valido no formato:
{"mode":"plan","steps":[{"capability":"<name>","arguments":{...}}]}
Nao invente capabilities.
Nao execute nem recomende acoes destrutivas sem confirmacao explicita.
Nao salve ou exponha senhas, tokens, chaves privadas ou dados sensiveis.
'@
$body = @{
  model = 'argos-qwen3:4b'
  from = 'qwen3:4b'
  system = $system
  parameters = @{ temperature = 0.2; top_p = 0.9 }
  stream = $false
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri 'http://localhost:11434/api/create' -Method Post -ContentType 'application/json' -Body $body
```

## Troubleshooting

- `ollama` nao reconhecido: o CLI do Ollama nao esta instalado ou nao esta no `PATH`
- `ConnectError` ou connection refused: o daemon do Ollama nao esta rodando em `localhost:11434`
- `{"models":[]}` em `/api/tags`: o daemon esta ativo, mas nenhum modelo foi baixado
- planner retornando formato inesperado: atualizar o codigo e repetir, pois o planner normaliza formatos comuns como `capability/arguments` e `action/<fields>`
- primeira resposta lenta: normalmente e carregamento frio do modelo; as chamadas seguintes tendem a ser mais rapidas por causa de `keep_alive`
