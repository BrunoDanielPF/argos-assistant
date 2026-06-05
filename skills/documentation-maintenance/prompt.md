# Documentacao do Argos

Use esta skill ao criar ou revisar documentacao do Argos.

Padrao:
- Escrever documentacao em portugues por padrao.
- Usar ingles apenas em comandos, nomes de bibliotecas, APIs, mensagens tecnicas existentes ou exemplos que precisem refletir o comportamento real.
- Manter o contexto do produto claro: Argos e um assistente local, offline-first, acionavel por CLI hoje e por voz/background no roadmap.
- Separar estado atual, roadmap e comandos disponiveis para evitar prometer funcionalidades ainda nao implementadas.
- Documentar seguranca sempre que houver execucao local, ferramentas, MCP, skills, voz ou automacao do computador.

Workflow:
- Identificar o publico do documento: usuario, desenvolvedor ou mantenedor.
- Atualizar README quando a mudanca afetar setup, uso, roadmap ou contexto geral.
- Atualizar docs especificos quando a mudanca for arquitetural ou operacional.
- Evitar documentacao duplicada; preferir um ponto canonico e referencias curtas.
- Rodar testes quando a documentacao acompanhar mudancas de comportamento ou catalogo.

Saida esperada:
- Texto em portugues, direto e verificavel.
- Secoes com estado atual versus futuro planejado.
- Comandos em blocos de codigo.
- Lista de validacao executada quando aplicavel.
