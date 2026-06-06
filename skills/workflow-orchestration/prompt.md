# Orquestracao de Workflows

Use esta skill ao planejar fluxos longos, assincronos ou residentes do Argos.

Decisao arquitetural:
- Manter o core atual simples enquanto o Argos ainda roda principalmente por CLI.
- Considerar LangGraph de forma incremental quando houver tarefas assincronas, modo residente, checkpoints, retomada ou human-in-the-loop.
- Usar LangChain apenas quando uma integracao concreta justificar a dependencia.

Workflow recomendado:
- Modelar o fluxo como estados explicitos: entrada, contexto, memoria, planejamento, politica, confirmacao, execucao, persistencia e resposta.
- Separar passos que podem pausar ou retomar, como confirmacao humana e execucao longa.
- Manter efeitos colaterais atras do executor e da politica de seguranca.
- Definir quais dados entram no checkpoint e quais nao devem ser persistidos.
- Adicionar testes para fluxo feliz, cancelamento, erro, retomada e acao bloqueada.

Quando usar LangGraph:
- tarefas em segundo plano
- filas de comandos
- voz com confirmacao posterior
- acoes que precisam sobreviver a restart
- workflows com multiplas etapas e estados duraveis

Saida esperada:
- Grafo ou lista de estados.
- Eventos de entrada e saida.
- Pontos de confirmacao.
- Dados persistidos.
- Testes necessarios.
