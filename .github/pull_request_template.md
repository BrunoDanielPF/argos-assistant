# Pull Request

## Resumo

Descreva de forma curta e objetiva o que este PR altera.

Exemplo:

> Adiciona comandos iniciais para listar e aprovar memórias pendentes no Memory Engine.

## Motivação

Explique por que esta mudança é necessária.

```text
Problema atual:
Motivo da alteração:
Resultado esperado:
```

## Tipo de mudança

Marque uma ou mais opções:

* [ ] Bug fix
* [ ] Nova funcionalidade
* [ ] Refatoração
* [ ] Documentação
* [ ] Testes
* [ ] Segurança
* [ ] Performance
* [ ] CI/CD
* [ ] Configuração/setup
* [ ] Breaking change
* [ ] Outro

## Área afetada

Marque uma ou mais opções:

* [ ] CLI
* [ ] Gateway residente
* [ ] Jobs
* [ ] Memory Engine
* [ ] Context Engine
* [ ] Adaptive Workflows
* [ ] Tool SDK
* [ ] Recovery Harness
* [ ] Model Router
* [ ] Behavior Pack System
* [ ] Policy Engine
* [ ] Approval Inbox
* [ ] Audit Log
* [ ] Configuração
* [ ] Instalação/setup
* [ ] Compatibilidade com Windows
* [ ] Documentação
* [ ] Segurança
* [ ] Outro

## Mudanças realizadas

Liste as principais alterações feitas neste PR.

*
*
*

## Como testar

Explique como validar a mudança localmente.

Inclua comandos, cenários e resultados esperados.

```bash
# Exemplo
argos --help
```

Resultado esperado:

```text
Descreva o resultado esperado.
```

## Evidências de teste

Marque o que foi executado:

* [ ] Testes automatizados
* [ ] Teste manual via CLI
* [ ] Teste manual no Windows
* [ ] Teste com Ollama
* [ ] Teste sem Ollama
* [ ] Teste de fluxo com arquivos locais
* [ ] Teste de policy/approval
* [ ] Teste de regressão
* [ ] Não aplicável

Detalhes:

```text
Comandos executados:
Resultado:
Observações:
```

## Impacto em segurança

Esta alteração envolve alguma ação sensível?

* [ ] Leitura de arquivos
* [ ] Escrita de arquivos
* [ ] Remoção de arquivos
* [ ] Movimento de arquivos
* [ ] Execução de shell/comandos
* [ ] Instalação de dependências
* [ ] Uso de rede
* [ ] Uso de secrets/tokens/credenciais
* [ ] Persistência de memória
* [ ] Geração ou execução de workflows
* [ ] Geração ou execução de tools
* [ ] Alteração de policy
* [ ] Alteração de configuração
* [ ] Não envolve ação sensível

Se envolver ação sensível, explique as proteções aplicadas:

```text
Ação sensível:
Policy aplicada:
Confirmação necessária:
Auditoria gerada:
```

## Checklist de segurança

* [ ] Não incluí senhas, tokens, API keys, private keys, secrets ou credenciais.
* [ ] Não incluí logs com dados sensíveis.
* [ ] A mudança não salva dados sensíveis em memória.
* [ ] A mudança não executa comandos sem validação.
* [ ] A mudança não executa ação sensível sem confirmação quando necessário.
* [ ] A mudança não burla Policy Engine, Approval Inbox ou mecanismos de auditoria.
* [ ] A mudança respeita a regra: semântico para sugerir, determinístico para validar/autorizar/executar.
* [ ] Não aplicável.

## Impacto em memória e contexto

Esta alteração afeta memória ou contexto?

* [ ] Cria candidatos de memória
* [ ] Lê memórias existentes
* [ ] Salva memórias
* [ ] Altera classificação de memórias
* [ ] Altera escopo de memórias
* [ ] Altera recuperação de contexto
* [ ] Altera montagem de prompt/contexto
* [ ] Não afeta memória/contexto

Explique:

```text
Impacto:
Escopo:
Proteções:
```

## Impacto em workflows, jobs ou tools

Esta alteração afeta workflows, jobs ou tools?

* [ ] Cria workflow
* [ ] Valida workflow
* [ ] Executa workflow
* [ ] Agenda job
* [ ] Executa job
* [ ] Cria tool
* [ ] Executa tool
* [ ] Altera permissões de tool/workflow/job
* [ ] Não afeta workflows, jobs ou tools

Explique:

```text
Impacto:
Permissões:
Auditoria:
```

## Compatibilidade com Windows

O Argos tem foco inicial em Windows.

Marque o que foi considerado:

* [ ] Caminhos com `\` e `/`
* [ ] PowerShell
* [ ] Encoding UTF-8
* [ ] Espaços em nomes de pastas
* [ ] Permissões de arquivo
* [ ] Terminal Windows
* [ ] Compatibilidade com Ollama no Windows
* [ ] Não aplicável

Observações:

```text
Observações de compatibilidade:
```

## Breaking changes

Este PR quebra compatibilidade com comportamento, comandos, configuração ou dados existentes?

* [ ] Sim
* [ ] Não

Se sim, explique:

```text
O que quebra:
Como migrar:
Impacto para o usuário:
```

## Documentação

A documentação foi atualizada?

* [ ] README.md
* [ ] CONTRIBUTING.md
* [ ] SECURITY.md
* [ ] Documentação de CLI
* [ ] Documentação de arquitetura
* [ ] Exemplos
* [ ] Não precisava

Explique:

```text
Alterações de documentação:
```

## Issues relacionadas

Relacione issues, proposals ou discussões conectadas.

```text
Closes #
Related to #
Depends on #
```

## Checklist final

* [ ] O PR tem escopo claro.
* [ ] O código foi revisado localmente.
* [ ] Os testes relevantes foram executados.
* [ ] A documentação foi atualizada quando necessário.
* [ ] Não foram adicionados arquivos temporários, logs locais ou credenciais.
* [ ] A mudança respeita a arquitetura local-first do Argos.
* [ ] A mudança mantém o projeto agnóstico ao modelo.
* [ ] A mudança respeita segurança, policies, approvals e auditoria.
* [ ] O PR está pronto para revisão.

## Observações adicionais

Inclua qualquer contexto extra para quem for revisar.

```text
Observações:
```