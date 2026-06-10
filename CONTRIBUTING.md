# Guia de Contribuição do Argos

Obrigado por considerar contribuir com o Argos.

O Argos é um assistente pessoal local-first para Windows, desenvolvido em Python, integrado inicialmente ao Ollama, com foco em CLI, gateway residente, memória, tools, workflows, jobs, execução controlada, segurança e auditoria.

Este guia define como contribuir de forma organizada, segura e alinhada à visão do projeto.

## Visão do Projeto

O objetivo do Argos é transformar o computador do usuário em um ambiente agentável, seguro e extensível.

A visão do projeto é:

> Argos é um assistente local que entende contexto, lembra decisões, automatiza tarefas, executa tools aprovadas, audita ações e respeita políticas de segurança.

Princípios fundamentais:

* Local-first.
* Segurança por padrão.
* Arquitetura agnóstica ao modelo.
* Execução controlada por políticas.
* Ações sensíveis com confirmação.
* Auditoria de ações relevantes.
* Privacidade e proteção de dados do usuário.
* Código simples, testável e extensível.

## Código de Conduta

Todas as interações no projeto devem seguir o `CODE_OF_CONDUCT.md`.

Discussões técnicas são bem-vindas, inclusive discordâncias, desde que sejam feitas com respeito, clareza e foco na evolução do projeto.

## Como Contribuir

Você pode contribuir de várias formas:

* Reportando bugs.
* Sugerindo melhorias.
* Melhorando documentação.
* Criando ou revisando issues.
* Enviando pull requests.
* Escrevendo testes.
* Melhorando mensagens da CLI.
* Propondo novas tools, workflows ou integrações.
* Revisando segurança, permissões e arquitetura.

Antes de abrir uma grande mudança, prefira criar uma issue explicando a proposta.

## Tipos de Contribuição

### Correção de bug

Use uma issue ou pull request descrevendo:

* comportamento atual;
* comportamento esperado;
* passos para reproduzir;
* logs relevantes, sem dados sensíveis;
* ambiente utilizado, quando necessário.

### Nova funcionalidade

Para novas funcionalidades, descreva:

* problema que a funcionalidade resolve;
* proposta de solução;
* impacto na arquitetura;
* impacto em segurança;
* comandos CLI afetados;
* arquivos ou módulos afetados;
* critérios de aceite;
* testes previstos.

### Documentação

Melhorias de documentação são bem-vindas.

Incluem:

* README;
* exemplos de uso;
* explicações de arquitetura;
* guias de instalação;
* guias de contribuição;
* comentários úteis em código;
* documentação de tools, workflows e configurações.

### Refatoração

Refatorações devem manter o comportamento existente, salvo quando a mudança for explicitamente descrita.

Ao propor refatorações, explique:

* qual problema técnico está sendo resolvido;
* quais módulos foram afetados;
* quais testes garantem que o comportamento foi preservado.

## Segurança e Privacidade

Segurança é parte central do Argos.

Não envie para issues, pull requests, commits, exemplos, logs ou documentação:

* senhas;
* tokens;
* API keys;
* private keys;
* secrets;
* credenciais;
* dados pessoais de terceiros;
* logs contendo informações sensíveis.

Se uma credencial for exposta acidentalmente, revogue-a imediatamente.

Também não serão aceitas contribuições que:

* burlem políticas de segurança;
* executem comandos destrutivos sem confirmação;
* escondam telemetria ou coleta de dados;
* instalem dependências sem transparência;
* movam, editem ou removam arquivos sem controle;
* salvem dados sensíveis em memória;
* exponham dados do usuário em logs ou auditoria;
* executem código arbitrário gerado por modelo sem validação.

O Argos deve seguir a regra:

> Semântico para buscar, sugerir e contextualizar. Determinístico para validar, autorizar e executar.

## Diretrizes de Arquitetura

Ao contribuir, mantenha a arquitetura alinhada aos seguintes princípios:

### 1. Não acoplar o Argos a um único modelo

O Argos deve funcionar com diferentes modelos locais e, no futuro, com diferentes provedores.

Evite implementar regras de negócio diretamente dependentes de um modelo específico do Ollama.

### 2. Não deixar o LLM autorizar ações sensíveis

O modelo pode sugerir, classificar ou estruturar uma resposta, mas não deve ser a fonte final de autorização.

Ações sensíveis devem passar por policy, validação e confirmação quando necessário.

### 3. Separar sugestão de execução

Uma proposta gerada por IA deve virar uma estrutura validável antes de qualquer execução.

Exemplos:

* memória candidata;
* workflow em draft;
* plano de recuperação;
* proposta de tool;
* plano de ação.

### 4. Preservar auditabilidade

Ações relevantes devem poder ser inspecionadas depois.

Sempre que uma contribuição adicionar execução, automação ou persistência, considere como isso será auditado.

### 5. Evitar efeitos colaterais inesperados

Código que escreve arquivos, move arquivos, executa shell, instala dependências ou altera configuração deve ser tratado como sensível.

Essas ações devem ser explícitas, controladas e testáveis.

## Áreas Principais do Projeto

As principais áreas previstas ou existentes no Argos incluem:

* CLI;
* gateway residente;
* jobs;
* memória de sessão;
* memória persistente;
* Memory Engine;
* Context Engine;
* Adaptive Workflows;
* Tool SDK;
* Recovery Harness;
* Model Router;
* Behavior Pack System;
* Policy Engine;
* Approval Inbox;
* Audit Log;
* integrações locais;
* integração com Ollama;
* documentação e experiência de instalação.

Ao criar uma contribuição, tente manter a mudança dentro de um escopo claro.

## Padrão para Issues

Ao abrir uma issue, use um título claro.

Exemplos:

```text
bug: erro ao carregar configuração local
feature: adicionar comando argos memory list
docs: melhorar guia de instalação no Windows
security: revisar política de execução de shell
refactor: separar planner da execução de tools
```

Sempre que possível, inclua:

```text
## Contexto

Explique o problema ou oportunidade.

## Comportamento atual

Descreva como funciona hoje.

## Comportamento esperado

Descreva o que deveria acontecer.

## Proposta

Explique uma possível solução.

## Critérios de aceite

- [ ] Critério 1
- [ ] Critério 2
- [ ] Critério 3

## Observações

Inclua logs, prints ou detalhes adicionais, sem dados sensíveis.
```

## Padrão para Pull Requests

Antes de abrir um pull request:

* verifique se a mudança tem escopo claro;
* rode os testes disponíveis;
* atualize documentação se necessário;
* evite incluir arquivos temporários;
* remova logs locais;
* não envie credenciais;
* explique decisões relevantes.

Modelo recomendado:

```text
## Resumo

Descreva o que foi alterado.

## Motivação

Explique por que a mudança é necessária.

## Mudanças realizadas

- Item 1
- Item 2
- Item 3

## Como testar

Explique como validar a mudança.

## Impacto em segurança

Informe se a mudança envolve:
- leitura de arquivos;
- escrita de arquivos;
- execução de shell;
- uso de tools;
- workflows;
- memória;
- logs;
- credenciais;
- rede;
- automações.

## Checklist

- [ ] Testei localmente
- [ ] Atualizei documentação quando necessário
- [ ] Não incluí dados sensíveis
- [ ] A mudança respeita as policies do projeto
- [ ] A mudança não executa ação sensível sem confirmação
```

## Convenção de Commits

Prefira commits pequenos e objetivos.

Sugestão de prefixos:

```text
feat: nova funcionalidade
fix: correção de bug
docs: documentação
test: testes
refactor: refatoração sem mudança de comportamento
chore: tarefas auxiliares
security: melhoria ou correção de segurança
ci: mudanças em pipeline
```

Exemplos:

```text
feat: adicionar comando argos memory pending
fix: corrigir carregamento de config no Windows
docs: adicionar guia de contribuição
security: bloquear secrets em candidatos de memória
refactor: separar validação de workflow do runner
```

## Branches

Use nomes de branch descritivos.

Exemplos:

```text
feature/memory-engine
fix/config-loader-windows
docs/contributing-guide
security/block-secret-memory
refactor/workflow-validator
```

## Testes

Toda mudança relevante deve incluir ou atualizar testes quando possível.

Priorize testes para:

* regras de policy;
* classificação de memória;
* bloqueio de secrets;
* geração e validação de workflows;
* execução de tools;
* recuperação de falhas;
* roteamento de modelos;
* comandos CLI;
* persistência em SQLite;
* leitura e escrita de configuração.

Mudanças que envolvem execução local, arquivos, shell ou automação devem ter testes cuidadosos para evitar efeitos colaterais.

## Desenvolvimento Local

As instruções exatas de setup podem evoluir com o projeto. Em geral, espera-se um ambiente com:

* Python;
* Git;
* Ollama, quando necessário;
* dependências do projeto instaladas;
* terminal compatível com Windows.

Fluxo geral esperado:

```bash
git clone https://github.com/BrunoDanielPF/argos-assistant.git
cd argos-assistant
```

Depois, siga as instruções atuais do `README.md`.

Caso o projeto use ambiente virtual Python, prefira isolar dependências em `.venv`.

## Configurações Locais

Arquivos locais de configuração, credenciais e estado do usuário não devem ser commitados.

Evite versionar:

```text
.env
.venv/
__pycache__/
*.log
*.sqlite
*.db
.local
secrets.*
config.local.*
```

Configurações sensíveis devem ficar fora do repositório.

## Dependências

Ao adicionar dependências:

* justifique a necessidade;
* prefira bibliotecas maduras e mantidas;
* evite dependências pesadas sem motivo claro;
* avalie impacto em segurança;
* avalie compatibilidade com Windows;
* atualize arquivos de dependência do projeto;
* documente qualquer requisito adicional de instalação.

Não adicione frameworks complexos sem alinhamento prévio em issue.

## Contribuições com Tools

Tools devem ser seguras, explícitas e auditáveis.

Ao propor uma nova tool, descreva:

* nome;
* objetivo;
* entradas;
* saídas;
* permissões necessárias;
* riscos;
* exemplos de uso;
* ações com efeito colateral;
* como testar;
* como auditar.

Tools não devem:

* executar comandos arbitrários sem validação;
* ler diretórios sensíveis sem permissão explícita;
* escrever ou remover arquivos sem confirmação;
* expor secrets;
* enviar dados para serviços externos sem consentimento.

## Contribuições com Workflows

Workflows devem ser declarativos, validados e aprováveis.

Ao propor um workflow, descreva:

* gatilho;
* passos;
* permissões;
* limites;
* ações sensíveis;
* comportamento esperado;
* logs gerados;
* estratégia de falha;
* critérios de aprovação.

Workflows gerados por modelo não devem ser executados diretamente.

O ciclo esperado é:

```text
draft -> validated -> approved -> enabled
```

## Contribuições com Memória

Mudanças relacionadas à memória devem respeitar:

* escopo da memória;
* classificação por tipo;
* status;
* confirmação para memórias importantes;
* bloqueio de dados sensíveis;
* auditoria;
* exclusão ou arquivamento quando solicitado.

Nunca salve automaticamente:

* senhas;
* tokens;
* secrets;
* private keys;
* credenciais;
* dados pessoais sensíveis.

## Contribuições com Recovery

O mecanismo de recuperação deve sempre respeitar policy.

Recuperações automáticas só devem ocorrer em situações seguras, como:

* retry de leitura;
* retry após timeout;
* reconstrução de contexto;
* consulta de status;
* geração de resposta parcial.

Devem exigir confirmação:

* escrita de arquivos;
* execução de shell;
* instalação de dependência;
* alteração de configuração;
* habilitação de workflow;
* uso de tool com efeito colateral.

## Compatibilidade com Windows

O Argos tem foco inicial em Windows.

Ao contribuir, considere:

* caminhos com `\` e `/`;
* PowerShell;
* permissões de arquivos;
* encoding UTF-8;
* espaços em nomes de pastas;
* comportamento de terminal;
* compatibilidade com Ollama no Windows.

Evite assumir comportamento exclusivo de Linux/macOS sem fallback ou documentação.

## Documentação de Decisões

Mudanças arquiteturais importantes devem ser documentadas.

Quando uma decisão for relevante, explique:

* contexto;
* alternativas consideradas;
* decisão tomada;
* consequências;
* impacto em segurança;
* impacto em manutenção.

Isso ajuda o projeto a manter consistência ao longo do tempo.

## Revisão de Código

Pull requests serão avaliados considerando:

* clareza;
* segurança;
* simplicidade;
* alinhamento com a visão do Argos;
* testes;
* documentação;
* impacto em usuários;
* impacto em manutenção;
* compatibilidade com Windows;
* respeito às políticas do projeto.

Mantenedores podem solicitar alterações antes da aprovação.

## O que Evitar

Evite contribuições que:

* aumentem complexidade sem necessidade;
* adicionem dependências pesadas sem justificativa;
* misturem muitas mudanças em um único PR;
* executem ações perigosas sem confirmação;
* acoplem o projeto a um modelo específico;
* salvem dados sensíveis;
* dificultem auditoria;
* ignorem compatibilidade com o sistema operacional;
* criem automações difíceis de explicar;
* alterem comportamento global sem documentação.

## Licença

Ao contribuir com o projeto, você concorda que sua contribuição será disponibilizada sob a mesma licença do repositório, salvo indicação explícita em contrário.

## Dúvidas

Se tiver dúvida antes de contribuir, abra uma issue com contexto suficiente.

Prefira perguntar antes de implementar grandes mudanças.

Contribuições são bem-vindas quando ajudam o Argos a evoluir como um assistente local-first, seguro, auditável, extensível e útil para o usuário.
