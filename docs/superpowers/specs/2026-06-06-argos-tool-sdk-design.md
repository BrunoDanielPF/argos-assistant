# Argos Tool SDK

## Objetivo

Transformar as capacidades executaveis do Argos em tools portateis, descobertas dinamicamente e governadas por contrato, lifecycle, permissoes e politica. Quando nenhuma tool atender uma solicitacao, o Argos podera propor e gerar uma nova tool em estado `draft`, mas nunca instala-la ou executa-la sem validacao e aprovacao explicita.

## Escopo do primeiro incremento

O primeiro incremento entrega:

- contrato `tool.yaml` versionado;
- schemas de entrada e saida em JSON Schema Draft 2020-12;
- loader e catalogo dinamico;
- lifecycle persistido fora do manifesto;
- validacao estrutural, semantica e estatica;
- execucao de tools aprovadas em subprocesso;
- ambiente virtual separado por tool;
- timeout, limite de saida e ambiente filtrado;
- politica baseada nas permissoes declaradas;
- auditoria de validacao, aprovacao e execucao;
- geracao de scaffold em estado `draft`;
- tool demonstrativa `local.spring.create_project`.

Ficam fora deste incremento:

- execucao automatica de codigo recem-gerado;
- sandbox forte de codigo nao confiavel;
- download automatico de tools;
- marketplace;
- assinatura criptografica;
- adaptador MCP;
- instalacao automatica de dependencias da internet durante uma conversa.

## Principios

1. Tool, skill, capability e MCP sao conceitos separados.
2. O modelo nunca executa codigo diretamente.
3. Uma tool desconhecida e bloqueada antes da confirmacao.
4. O manifesto descreve o contrato; o Argos controla o estado operacional.
5. Permissoes sao minimas, explicitas e exibidas antes da aprovacao.
6. Inputs e outputs sao validados.
7. `venv` isola dependencias, mas nao e considerado sandbox.
8. Codigo gerado permanece inativo ate revisao e aprovacao.
9. A mesma definicao de tool deve ser adaptavel ao MCP no futuro.

## Terminologia

- **Skill:** instrucao ou conhecimento carregado pelo modelo.
- **Tool:** unidade executavel com contrato de entrada, saida e permissoes.
- **Capability:** autorizacao concedida para uma operacao.
- **MCP:** protocolo de descoberta e chamada de tools externas.
- **Tool SDK:** contratos e servicos usados para criar, validar, instalar, descobrir e executar tools.

## Layout

```text
%USERPROFILE%\.argos\
├── tools\
│   └── local.spring.create_project\
│       └── 1.0.0\
│           ├── tool.yaml
│           ├── handler.py
│           ├── requirements.lock
│           └── tests\
├── tool-drafts\
│   └── local.example.generated\
├── tool-envs\
│   └── local.spring.create_project-1.0.0\
├── tool-state.json
└── audit\
    └── tools.jsonl
```

O manifesto e o codigo instalado sao tratados como artefatos versionados. Estados como `approved`, `enabled` e `disabled` ficam em `tool-state.json`, evitando modificar o pacote da tool durante o uso.

## Manifesto

```yaml
schema_version: "1.0"
name: local.spring.create_project
version: "1.0.0"
title: Criar projeto Spring Boot
description: Cria uma estrutura inicial de backend Spring Boot.
runtime:
  type: python
  python: ">=3.12,<3.13"
  entrypoint: handler.py

input_schema:
  $schema: https://json-schema.org/draft/2020-12/schema
  type: object
  additionalProperties: false
  required:
    - name
    - directory
    - java_version
    - build_tool
    - group_id
  properties:
    name:
      type: string
      pattern: "^[a-z][a-z0-9-]{1,62}$"
    directory:
      type: string
      minLength: 1
    java_version:
      type: integer
      enum: [17, 21]
    build_tool:
      type: string
      enum: [maven, gradle]
    group_id:
      type: string
      pattern: "^[a-z][a-z0-9_.]+$"

output_schema:
  $schema: https://json-schema.org/draft/2020-12/schema
  type: object
  additionalProperties: false
  required: [project_path, created_files]
  properties:
    project_path:
      type: string
    created_files:
      type: array
      items:
        type: string

permissions:
  filesystem:
    read: []
    write:
      - "${directory}/**"
  network:
    enabled: false
    hosts: []
  subprocess:
    executables: []

execution:
  timeout_seconds: 60
  max_output_bytes: 1048576
```

Regras:

- `schema_version`, `name`, `version`, `runtime`, `input_schema`, `output_schema`, `permissions` e `execution` sao obrigatorios;
- propriedades desconhecidas no manifesto sao rejeitadas;
- nomes usam namespace e nao podem colidir;
- versoes seguem SemVer;
- schemas devem declarar Draft 2020-12;
- permissao de escrita usa placeholders vindos apenas de argumentos ja validados;
- wildcards amplos como `C:\**` e `%USERPROFILE%\**` sao rejeitados.

## Lifecycle

```text
draft
  -> validating
  -> validated
  -> approved
  -> installed
  -> enabled
```

Estados alternativos:

- `rejected`: validacao ou aprovacao negada;
- `disabled`: instalada, mas indisponivel para o planner;
- `broken`: falha de integridade ou ambiente.

Transicoes sao controladas pelo Argos. A IA pode criar `draft`, mas nao pode conceder `approved`, `installed` ou `enabled`.

## Validacao

Uma tool passa pelas seguintes etapas:

1. validar YAML seguro;
2. validar manifesto contra o meta-schema do SDK;
3. validar `input_schema` e `output_schema` como JSON Schema 2020-12;
4. verificar nome, versao e entrypoint;
5. impedir caminhos absolutos ou traversal no entrypoint;
6. verificar que arquivos declarados existem;
7. analisar Python por AST;
8. sinalizar imports e chamadas de alto risco;
9. validar `requirements.lock`;
10. calcular SHA-256 dos arquivos;
11. registrar relatorio e auditoria.

A analise AST e um detector, nao uma sandbox. Ela pode bloquear padroes evidentes como `eval`, `exec`, `compile`, `ctypes`, import dinamico, `shell=True` e acesso direto a credenciais, mas nao prova que o codigo e seguro.

## Instalacao

1. O usuario solicita instalacao de um draft validado.
2. O Argos mostra nome, versao, origem, hashes e permissoes.
3. O usuario aprova explicitamente.
4. O pacote e copiado para `tools/<name>/<version>`.
5. Um `venv` exclusivo e criado.
6. Dependencias sao instaladas de `requirements.lock` com:

```text
pip install --require-hashes --only-binary :all: -r requirements.lock
```

7. O Argos registra hashes, estado e ambiente.
8. A tool permanece `installed` ate ser habilitada.

Tools sem dependencias usam um `requirements.lock` vazio e nao acessam a rede.

## Execucao

Tools aprovadas e habilitadas usam um protocolo JSON por `stdin/stdout`:

Entrada:

```json
{
  "protocol_version": "1.0",
  "tool": "local.spring.create_project",
  "invocation_id": "uuid",
  "arguments": {}
}
```

Saida:

```json
{
  "ok": true,
  "result": {},
  "error": null
}
```

O runner:

- valida argumentos;
- expande permissoes usando argumentos validados;
- aplica a politica do Argos;
- solicita confirmacao quando houver efeitos colaterais;
- inicia o Python do `venv` com lista de argumentos e `shell=False`;
- usa diretorio temporario como `cwd`;
- envia ambiente minimo;
- aplica timeout;
- limita stdout e stderr;
- rejeita saida nao JSON;
- valida o resultado;
- registra duracao, status e hashes.

No Windows, a evolucao prevista e usar Job Objects para controlar a arvore de processos e AppContainer ou Windows Sandbox para tools nao confiaveis.

## Integracao com o planner

O catalogo fornece ao planner somente tools `enabled`, com:

- nome;
- descricao;
- input schema reduzido;
- classificacao de risco.

Se nenhuma tool for adequada, o planner retorna:

```json
{
  "mode": "tool_proposal",
  "name": "local.spring.create_project",
  "reason": "Nao existe uma tool habilitada para criar projetos Spring Boot.",
  "required_inputs": [
    "name",
    "directory",
    "java_version",
    "build_tool",
    "group_id"
  ]
}
```

O agente pergunta se o usuario deseja gerar um draft. Uma resposta positiva chama o gerador de scaffold; ela nao executa a nova tool.

## Geracao de drafts

O gerador cria:

```text
tool.yaml
handler.py
requirements.lock
tests/test_handler.py
```

O SDK fornece templates deterministas. O modelo preenche descricao, schemas e logica especifica, mas o gerador valida nomes e caminhos antes de gravar.

Ao finalizar:

```text
Draft criado
-> validacao estrutural
-> analise estatica
-> relatorio
-> aguardar revisao e aprovacao
```

## Tool demonstrativa

`local.spring.create_project` sera uma tool bundled e confiavel, usada para provar o SDK.

Ela:

- coleta argumentos pelo fluxo de clarificacao do Argos;
- cria uma estrutura Maven ou Gradle sem usar shell;
- escreve arquivos diretamente com Python;
- nao usa rede;
- nao executa Maven ou Gradle;
- retorna todos os caminhos criados;
- falha se o diretorio de destino ja existir e nao estiver vazio.

## Compatibilidade MCP

O contrato interno deve mapear futuramente:

- catalogo -> `tools/list`;
- `input_schema` -> `inputSchema`;
- executor -> `tools/call`;
- erros de validacao -> erro de argumentos;
- erro da tool -> resultado com `isError`;
- namespace local -> nome prefixado para evitar colisao.

## Seguranca

- capabilities desconhecidas sao `blocked`;
- tools desabilitadas nao entram no prompt;
- confirmacao mostra argumentos e permissoes efetivas;
- secrets nao sao herdados no ambiente;
- rede e negada por padrao no contrato;
- o MVP nao afirma impedir rede apenas por executar subprocesso;
- a tool nao recebe o objeto do agente, memoria ou cliente Ollama;
- logs removem campos marcados como sensiveis;
- hashes detectam alteracao depois da aprovacao;
- alteracao de manifesto, codigo ou lock invalida a aprovacao.

## Criterios de aceite

- uma tool valida e habilitada aparece no catalogo;
- input invalido nao inicia subprocesso;
- tool desconhecida e bloqueada antes da confirmacao;
- tool desabilitada nao pode ser chamada;
- timeout encerra a chamada;
- output invalido gera erro controlado;
- mudanca de hash marca a tool como `broken`;
- draft gerado nunca e executado;
- instalacao exige aprovacao;
- a tool Spring cria um projeto minimo no diretorio autorizado;
- todos os eventos relevantes aparecem no audit JSONL.

## Referencias

- [JSON Schema Draft 2020-12](https://json-schema.org/specification)
- [Python plugin discovery](https://packaging.python.org/guides/creating-and-discovering-plugins/)
- [Python entry points](https://packaging.python.org/en/latest/specifications/entry-points/)
- [pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/)
- [Python subprocess](https://docs.python.org/3/library/subprocess.html)
- [MCP tools](https://modelcontextprotocol.io/docs/learn/server-concepts)
- [MCP security](https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
- [Windows Sandbox](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/windows-sandbox-configure-using-wsb-file)
