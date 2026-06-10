---
name: Feature request
about: Suggest an idea for this project
title: ''
labels: enhancement, inner-source
assignees: ''

---

---

name: Feature request
about: Proponha uma nova funcionalidade, melhoria ou evolução arquitetural para o Argos
title: "feat: "
labels: ["feature", "needs-triage"]
assignees: ""
-------------

# Feature Request

## Resumo

Descreva de forma curta e objetiva a funcionalidade ou melhoria proposta.

Exemplo:

> Adicionar comando `argos memory pending` para listar memórias aguardando aprovação.

## Problema ou motivação

Qual problema essa funcionalidade resolve?

Explique o contexto, a dor atual ou a oportunidade de melhoria.

```text
Hoje o Argos...
Isso causa...
A proposta ajudaria porque...
```

## Comportamento esperado

Descreva como o Argos deveria se comportar após essa funcionalidade.

```text
Quando o usuário...
O Argos deve...
O resultado esperado é...
```

## Tipo de melhoria

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
* [ ] Segurança
* [ ] Documentação
* [ ] Instalação/setup
* [ ] Compatibilidade com Windows
* [ ] Outro

## Proposta de solução

Descreva uma possível solução técnica ou funcional.

Se fizer sentido, inclua exemplos de comandos, fluxo esperado ou estrutura de arquivos.

```bash
argos exemplo comando
```

## Exemplo de uso

Mostre como o usuário usaria essa funcionalidade.

```text
Usuário:
"quando eu baixar um PDF, sugira mover para a pasta correta"

Argos:
"Criei um workflow em draft..."
```

## Impacto em segurança

Essa funcionalidade envolve alguma ação sensível?

* [ ] Leitura de arquivos
* [ ] Escrita de arquivos
* [ ] Remoção de arquivos
* [ ] Movimento de arquivos
* [ ] Execução de shell/comandos
* [ ] Instalação de dependências
* [ ] Uso de rede
* [ ] Uso de secrets/tokens/credenciais
* [ ] Persistência de memória
* [ ] Criação/habilitação de workflows
* [ ] Criação/habilitação de tools
* [ ] Não envolve ação sensível

Se envolver ação sensível, explique como deve ser protegida:

```text
Ação sensível:
Proteção esperada:
Confirmação necessária:
Auditoria esperada:
```

## Política esperada

Como essa funcionalidade deve se comportar em relação às policies do Argos?

* [ ] Pode executar automaticamente
* [ ] Deve pedir confirmação
* [ ] Deve criar item pendente em Approval Inbox
* [ ] Deve ser bloqueada por padrão
* [ ] Ainda precisa ser definido

Explique:

```text
Policy esperada:
Motivo:
```

## Impacto em memória/contexto

Essa funcionalidade deve usar ou alterar memória/contexto?

* [ ] Recupera memórias relevantes
* [ ] Cria candidatos de memória
* [ ] Salva memória automaticamente
* [ ] Cria memória pendente para aprovação
* [ ] Usa Context Engine
* [ ] Não usa memória/contexto
* [ ] Ainda precisa ser definido

Explique:

```text
Escopo esperado:
Tipo de memória/contexto:
```

## Impacto em auditoria

Essa funcionalidade deve gerar logs ou registros auditáveis?

* [ ] Sim
* [ ] Não
* [ ] Ainda precisa ser definido

Se sim, o que deve ser registrado?

```text
- Ação executada
- Permissões usadas
- Confirmação do usuário
- Arquivos afetados
- Modelo usado
- Workflow/job relacionado
```

## Critérios de aceite

Liste os critérios objetivos para considerar essa feature concluída.

* [ ] Critério 1
* [ ] Critério 2
* [ ] Critério 3

Exemplo:

* [ ] O comando `argos memory pending` lista memórias com status `pending`.
* [ ] O comando não exibe secrets ou credenciais.
* [ ] O resultado mostra id, tipo, escopo, conteúdo resumido e data de criação.
* [ ] Existem testes cobrindo o comportamento esperado.

## Alternativas consideradas

Descreva alternativas que foram consideradas e por que não foram escolhidas.

```text
Alternativa 1:
Motivo para não seguir:

Alternativa 2:
Motivo para não seguir:
```

## Dependências ou pré-requisitos

Esta feature depende de outra issue, módulo ou decisão?

```text
Depende de:
Relacionado a:
Bloqueado por:
```

## Informações adicionais

Inclua qualquer contexto extra, prints, diagramas, referências ou observações úteis.

Não inclua senhas, tokens, API keys, private keys, secrets ou dados pessoais sensíveis.
