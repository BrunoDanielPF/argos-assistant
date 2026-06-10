# Argos

Argos é um assistente pessoal local para Windows, pensado para transformar o computador em um ambiente mais inteligente, organizado, automatizável e seguro.

A proposta do Argos não é apenas responder perguntas. A proposta é permitir que o usuário converse com o próprio computador, peça ajuda em linguagem natural, delegue pequenas ações, crie rotinas, receba alertas, mantenha contexto entre sessões e continue no controle de tudo que pode alterar arquivos, executar comandos ou afetar o ambiente local.

Em sua forma final, o Argos deve funcionar como uma camada de assistência sobre o sistema operacional: um copiloto local que entende o ambiente do usuário, aprende preferências com autorização, ajuda a operar projetos e arquivos, propõe automações úteis e executa ações de forma segura, rastreável e reversível sempre que possível.

## Objetivo final

O objetivo final do Argos é ser um assistente local residente, capaz de acompanhar a jornada diária do usuário no computador.

Ele deve ajudar o usuário a:

- iniciar o dia com contexto sobre tarefas, projetos e pendências;
- encontrar arquivos, pastas, programas e informações locais sem depender de navegação manual;
- organizar documentos e downloads com sugestões claras;
- lembrar preferências, decisões e procedimentos importantes;
- automatizar rotinas repetitivas sem abrir mão de aprovação humana;
- monitorar eventos importantes, como falhas, jobs, arquivos novos ou tarefas recorrentes;
- explicar o que aconteceu quando algo falhar;
- sugerir recuperação segura em vez de apenas interromper a experiência;
- manter um histórico compreensível do que foi feito, quando foi feito e com qual autorização.

O Argos deve evoluir para ser menos uma ferramenta de comando e mais um ambiente de apoio contínuo ao uso do computador.

## Promessa do produto

A promessa do Argos é:

> **Ajudar o usuário a operar o próprio computador com mais contexto, menos repetição e mais segurança.**

Isso significa que o Argos deve ser útil sem ser invasivo, autônomo sem ser imprevisível e inteligente sem tirar o controle do usuário.

O usuário deve sentir que o Argos:

- entende o que ele está tentando fazer;
- lembra do que é importante, mas não guarda informações sensíveis;
- sugere próximos passos úteis;
- pede confirmação antes de ações com impacto real;
- explica suas decisões de forma clara;
- consegue ser corrigido e melhorar com o uso;
- não depende obrigatoriamente de nuvem para funcionar;
- respeita o ambiente local como espaço privado do usuário.

## Jornada de uso esperada

A experiência do Argos deve ser construída em torno da jornada real do usuário no computador, não em torno de uma lista de comandos.

### 1. Primeiro contato

No primeiro uso, o Argos deve ajudar o usuário a configurar um ambiente funcional sem exigir conhecimento técnico profundo.

A experiência esperada é:

```text
Argos verifica o ambiente local.
Argos identifica o que já está disponível.
Argos sugere uma configuração inicial segura.
Argos explica o que pode fazer e o que precisa de autorização.
Usuário aprova o modo de funcionamento.
```

O objetivo desse momento é reduzir fricção. O usuário não deve precisar entender todos os detalhes internos para começar. Ele deve conseguir aceitar uma configuração recomendada e ajustar depois, se quiser.

### 2. Uso diário

No uso diário, o Argos deve ajudar em tarefas simples e frequentes.

Exemplos de intenção:

```text
Abra meu projeto principal.
Encontre aquele PDF da faculdade.
Crie uma nota com essas ideias.
Organize esse arquivo na pasta certa.
Mostre o que ficou pendente.
Resuma o que aconteceu na última execução.
```

A experiência deve ser natural. O usuário não deve precisar decorar muitos comandos. O Argos deve interpretar a intenção, propor um caminho e confirmar quando houver risco.

### 3. Organização do ambiente

O Argos deve ajudar o usuário a manter o computador organizado.

Isso inclui arquivos, downloads, documentos, projetos, notas, ferramentas e rotinas.

A expectativa não é que o Argos mova tudo sozinho. A expectativa é que ele observe padrões, faça sugestões e peça autorização antes de alterar algo.

Exemplo:

```text
Detectei um novo PDF em Downloads.
Ele parece ser um documento acadêmico.
Posso sugerir uma pasta para organizar?
```

Com o tempo, o usuário pode transformar sugestões recorrentes em automações aprovadas.

### 4. Trabalho com projetos

Para projetos de desenvolvimento, estudo ou organização pessoal, o Argos deve funcionar como um assistente contextual.

Ele deve conseguir entender que um projeto possui arquivos, decisões, comandos, problemas recorrentes, ferramentas e histórico.

A expectativa é que o usuário possa perguntar:

```text
O que eu estava fazendo neste projeto?
Quais decisões importantes já tomamos?
Como rodo esse ambiente?
O que falhou na última vez?
Qual arquivo parece estar relacionado com esse problema?
```

O Argos deve responder usando contexto local, memórias aprovadas e histórico relevante, sem misturar informações de projetos diferentes.

### 5. Criação de rotinas

A evolução natural do Argos é permitir que o usuário descreva rotinas em linguagem natural.

Exemplos:

```text
Todo dia de manhã, mostre um resumo das minhas pendências.
Quando eu baixar um PDF, me pergunte se quero organizar.
Quando um job falhar, me avise e sugira recuperação.
Quando eu abrir este projeto, verifique se há tarefas pendentes.
```

Essas rotinas não devem nascer executando ações sensíveis automaticamente. Elas devem ser propostas, revisadas, aprovadas e só então ativadas.

A expectativa é que o Argos ajude o usuário a programar comportamentos do computador sem precisar escrever scripts para tudo.

### 6. Falhas e recuperação

Quando algo falhar, o Argos não deve apenas exibir uma mensagem genérica de erro.

A experiência esperada é:

```text
O Argos identifica que houve uma falha.
O Argos explica o tipo provável do problema.
O Argos mostra opções seguras.
O Argos pede autorização antes de tentar algo com efeito colateral.
O Argos registra a tentativa para auditoria.
```

Exemplo:

```text
O modelo local demorou para responder.
Posso tentar novamente com uma configuração mais leve ou responder parcialmente agora.
```

O objetivo é transformar falhas em diagnóstico, recuperação e aprendizado.

## Como o Argos deve se comportar

O comportamento esperado do Argos deve seguir alguns princípios simples.

### Deve ser claro

O usuário precisa entender o que o Argos pretende fazer.

Antes de alterar algo, o Argos deve explicar a ação em linguagem direta.

### Deve ser cuidadoso

Ações que escrevem, movem, apagam, executam comandos, instalam ferramentas ou mudam configurações devem exigir confirmação.

### Deve ser útil sem ser invasivo

O Argos pode sugerir, lembrar e automatizar, mas não deve assumir controle do computador sem permissão.

### Deve aprender com autorização

O Argos deve aprender preferências, decisões e padrões úteis, mas deve bloquear senhas, tokens, credenciais e dados sensíveis.

### Deve ser local-first

Sempre que possível, dados, memória, execução e configuração devem permanecer na máquina do usuário.

### Deve ser explicável

O usuário deve conseguir perguntar o que o Argos fez, por que fez e com base em qual autorização.

## Expectativas de usabilidade

A usabilidade do Argos deve ser guiada por confiança.

O usuário deve conseguir usar o Argos em três níveis:

### Modo conversa

O usuário pede ajuda, tira dúvidas, resume informações e recebe orientação.

Nesse modo, o Argos não executa ações com efeito real sem confirmação.

### Modo assistido

O usuário pede uma ação local, como abrir arquivo, criar nota, buscar documento ou preparar uma rotina.

O Argos interpreta, mostra o plano quando necessário e pede aprovação para ações sensíveis.

### Modo residente

O Argos acompanha eventos locais, executa rotinas aprovadas, envia notificações e ajuda o usuário a manter o ambiente organizado.

Mesmo nesse modo, ações sensíveis continuam exigindo política e autorização.

## O que o Argos não deve ser

O Argos não deve ser um executor cego de comandos.

Também não deve ser um agente que decide sozinho alterar o computador do usuário.

Ele não deve:

- salvar segredos como memória;
- executar comandos destrutivos automaticamente;
- mover ou apagar arquivos sem confirmação;
- instalar ferramentas sem aprovação;
- habilitar automações sem revisão;
- esconder do usuário o que fez;
- depender de um único modelo ou provedor como base permanente;
- misturar linguagem técnica com experiência de produto para o usuário final.

## Experiência final desejada

A experiência final desejada é que o usuário possa abrir o computador e contar com o Argos como uma camada de apoio contínua.

Um cenário ideal:

```text
O usuário inicia o computador.
Argos apresenta um resumo curto do dia.
Argos mostra pendências relevantes.
Argos lembra o contexto dos projetos ativos.
Argos sugere ações úteis.
Argos observa eventos aprovados.
Argos pede confirmação para ações sensíveis.
Argos registra o que executou.
Argos aprende padrões com autorização.
```

O Argos deve reduzir esforço operacional, diminuir repetição e aumentar a sensação de controle sobre o ambiente local.

## Direção do produto

A direção do produto é construir um assistente local que combine:

- conversa natural;
- contexto do ambiente;
- memória segura;
- automações aprovadas;
- execução controlada;
- recuperação de falhas;
- rastreabilidade;
- adaptação ao usuário;
- funcionamento local sempre que possível.

Essa direção pode ser resumida assim:

> **Argos deve entender o ambiente, ajudar o usuário a agir, automatizar com consentimento e manter tudo explicável.**

## Documentação técnica

Este documento descreve a visão executiva, a jornada de uso e as expectativas do produto.

Detalhes técnicos, arquitetura interna, fluxos, módulos, decisões de implementação e critérios de aceite devem ficar separados em:

```text
docs/ARCHITECTURE.md
```

Essa separação é intencional: o README deve explicar o produto e a experiência esperada; a documentação técnica deve explicar como o Argos será construído.

## Status do projeto

O Argos está em construção ativa.

A versão atual deve ser entendida como uma base inicial para validar a experiência de um assistente local controlado pelo usuário. A expectativa do projeto é evoluir gradualmente até se tornar um assistente residente, seguro e contextual para o computador pessoal.