# File Resolution and Clarification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar edicao segura de arquivos com busca aproximada e clarificacoes respondidas por numero ou linguagem natural.

**Architecture:** O planner produz e resolve clarificacoes estruturadas, a memoria mantem a operacao pendente, o agente resolve referencias de arquivo antes da politica e o executor realiza somente escritas explicitas. A busca aproximada fica isolada em um componente deterministico e testavel.

**Tech Stack:** Python 3.12, Pydantic, pathlib, difflib, pytest, Ollama.

---

### Task 1: Estado de clarificacao

**Files:**
- Modify: `src/assistant/models.py`
- Modify: `src/assistant/memory/session.py`
- Test: `tests/test_memory.py`

- [ ] Criar testes para salvar, ler e limpar `pending_clarification`.
- [ ] Executar os testes e confirmar falha pela ausencia do estado.
- [ ] Adicionar o campo ao contexto e metodos dedicados na memoria.
- [ ] Executar os testes e confirmar sucesso.

### Task 2: Contrato do planner

**Files:**
- Modify: `src/assistant/planner.py`
- Test: `tests/test_planner.py`

- [ ] Criar testes para pedidos de edicao sem modo.
- [ ] Criar testes para respostas `1`, `substituir`, `adicione no final` e respostas incertas.
- [ ] Executar os testes e confirmar as falhas esperadas.
- [ ] Implementar `mode=clarification`, extracao da edicao e resolucao contextual.
- [ ] Restringir o fallback semantico as opcoes da clarificacao.
- [ ] Executar os testes e confirmar sucesso.

### Task 3: Resolucao aproximada

**Files:**
- Create: `src/assistant/files/resolver.py`
- Create: `src/assistant/files/__init__.py`
- Test: `tests/test_file_resolver.py`

- [ ] Criar testes para nome exato sem extensao, erro de digitacao, ambiguidade e ausencia.
- [ ] Executar os testes e confirmar falha pela ausencia do resolvedor.
- [ ] Implementar ranking por stem, nome completo e `SequenceMatcher`.
- [ ] Limitar busca e retornar estados `resolved`, `ambiguous` e `not_found`.
- [ ] Executar os testes e confirmar sucesso.

### Task 4: Orquestracao no agente

**Files:**
- Modify: `src/assistant/agent.py`
- Modify: `src/assistant/cli.py`
- Test: `tests/test_agent.py`

- [ ] Criar testes para persistir clarificacao e retomar a operacao.
- [ ] Criar testes para arquivo resolvido e selecao entre candidatos.
- [ ] Executar os testes e confirmar falha.
- [ ] Integrar memoria pendente e `FileResolver` antes da politica.
- [ ] Garantir que cancelamento e conclusao limpem o estado.
- [ ] Executar os testes e confirmar sucesso.

### Task 5: Escrita segura

**Files:**
- Modify: `src/assistant/execution/executor.py`
- Modify: `src/assistant/capabilities/registry.py`
- Modify: `src/assistant/execution/policy.py`
- Test: `tests/test_executor.py`
- Test: `tests/test_registry.py`
- Test: `tests/test_policy.py`

- [ ] Criar testes de `replace`, `append`, arquivo ausente e modo invalido.
- [ ] Executar os testes e confirmar falha.
- [ ] Implementar `write_file` somente para arquivos existentes.
- [ ] Registrar a capability e manter politica `confirm`.
- [ ] Executar os testes e confirmar sucesso.

### Task 6: Documentacao e validacao

**Files:**
- Modify: `README.md`

- [ ] Documentar exemplos de busca aproximada e clarificacao natural.
- [ ] Atualizar o Mermaid do fluxo de arquivos.
- [ ] Executar `python -m pytest -q`.
- [ ] Executar teste manual com `hello_world` resolvendo `hello_world.md`.
- [ ] Executar `git diff --check` e revisar o diff.
