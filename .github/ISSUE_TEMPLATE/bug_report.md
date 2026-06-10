---
name: Bug report
about: Create a report to help us improve
title: ''
labels: bug
assignees: ''

---

---

name: Bug report
about: Reporte um erro, falha, comportamento inesperado ou problema de segurança no Argos
title: "bug: "
labels: ["bug", "needs-triage"]
assignees: ""
-------------

# Bug Report

## Resumo

Descreva o problema de forma curta e objetiva.

Exemplo:

> O comando `argos memory list` falha quando não existe banco SQLite inicializado.

## Comportamento atual

O que está acontecendo hoje?

```text
Ao executar...
O Argos retorna...
O comportamento observado é...
```

## Comportamento esperado

O que deveria acontecer?

```text
O Argos deveria...
```

## Passos para reproduzir

Liste os passos para reproduzir o problema.

```bash
1. Execute:
2. Depois:
3. Observe:
```

Exemplo:

```bash
argos memory list
```

## Resultado obtido

Cole a saída, erro ou stack trace relevante.

Remova qualquer dado sensível antes de enviar.

```text
Cole aqui o erro ou saída relevante.
```

## Ambiente

Preencha as informações conhecidas:

```text
Sistema operacional:
Versão do Windows:
Versão do Python:
Versão do Argos:
Terminal usado:
Ollama instalado: sim/não
Modelo usado:
Branch:
Commit:
```

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

## Severidade

Marque a opção que melhor descreve o impacto:

* [ ] Baixa — problema visual, texto incorreto ou comportamento menor
* [ ] Média — funcionalidade específica não funciona
* [ ] Alta — fluxo importante está quebrado
* [ ] Crítica — perda de dados, execução indevida, exposição de dados ou falha grave de segurança

## O bug envolve segurança?

* [ ] Sim
* [ ] Não
* [ ] Não sei

Se sim, marque os itens relacionados:

* [ ] Exposição de senha/token/secret/credencial
* [ ] Execução de comando sem confirmação
* [ ] Escrita ou remoção de arquivo sem confirmação
* [ ] Bypass de policy
* [ ] Log contendo dado sensível
* [ ] Memória salvando dado sensível
* [ ] Workflow executando ação indevida
* [ ] Tool com permissão excessiva
* [ ] Outro

Descreva com cuidado, sem publicar secrets reais:

```text
Descrição do risco:
Impacto possível:
```

## Arquivos, comandos ou workflows afetados

Informe o que foi afetado, se souber.

```text
Comando:
Arquivo:
Workflow:
Tool:
Job:
Configuração:
```

## Logs relevantes

Cole logs relevantes, removendo dados sensíveis.

Não envie:

* senhas;
* tokens;
* API keys;
* private keys;
* secrets;
* credenciais;
* dados pessoais de terceiros.

```text
Cole aqui logs relevantes.
```

## Acontece sempre?

* [ ] Sim, sempre
* [ ] Às vezes
* [ ] Aconteceu uma vez
* [ ] Não consegui reproduzir novamente

Explique:

```text
Frequência:
Condições em que ocorre:
```

## Solução temporária

Existe algum workaround?

```text
Sim/Não.
Se sim, descreva:
```

## Possível causa

Se você tiver uma suspeita técnica, descreva aqui.

```text
Acredito que pode estar relacionado a...
```

## Critérios para considerar corrigido

* [ ] O erro não ocorre mais no cenário descrito.
* [ ] O comportamento esperado foi implementado.
* [ ] Foram adicionados ou atualizados testes.
* [ ] A correção não expõe dados sensíveis.
* [ ] A correção respeita as policies do Argos.
* [ ] A documentação foi atualizada, se necessário.

## Informações adicionais

Inclua prints, contexto extra ou links relacionados.

Não inclua dados sensíveis.
