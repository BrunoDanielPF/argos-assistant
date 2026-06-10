# Política de Segurança

A segurança é um princípio central do Argos.

O Argos é um assistente local-first para Windows, com foco em CLI, gateway residente, memória, tools, workflows, jobs, execução controlada, permissões, aprovações e auditoria. Por isso, vulnerabilidades relacionadas a execução de comandos, acesso a arquivos, exposição de dados, memória persistente, workflows e tools são tratadas com prioridade.

## Versões Suportadas

Enquanto o Argos estiver em fase inicial de desenvolvimento, apenas a versão mais recente da branch principal será considerada suportada para correções de segurança.

| Versão / Branch                     | Suporte de Segurança |
| ----------------------------------- | -------------------- |
| `main` / versão mais recente        | Sim                  |
| versões antigas sem release oficial | Não                  |
| forks não oficiais                  | Não                  |

Quando o projeto passar a publicar releases estáveis, esta tabela será atualizada para indicar quais versões recebem correções de segurança.

## Como Reportar uma Vulnerabilidade

Se você encontrar uma vulnerabilidade de segurança no Argos, não abra uma issue pública com detalhes exploráveis.

Reporte a vulnerabilidade por um canal privado.

Contato para reportes de segurança:

```text
frandalozzo@gmail.com
```

Ao reportar, inclua o máximo de contexto possível:

* descrição da vulnerabilidade;
* impacto esperado;
* passos para reproduzir;
* versão, branch ou commit afetado;
* sistema operacional;
* versão do Python;
* configuração relevante do Argos;
* logs ou mensagens de erro, sem dados sensíveis reais;
* sugestão de correção, se houver.

Não envie senhas, tokens, API keys, private keys, secrets ou credenciais reais no relatório.

## O Que é Considerado Vulnerabilidade

Exemplos de vulnerabilidades relevantes para o Argos:

* execução de comando sem confirmação quando deveria exigir aprovação;
* bypass de policy, permissões ou Approval Inbox;
* workflow executando ação sensível sem validação;
* tool com permissão maior do que a declarada;
* gravação, movimentação ou remoção de arquivos sem confirmação adequada;
* exposição de dados pessoais, credenciais ou secrets em logs;
* salvamento indevido de senhas, tokens, API keys, private keys ou secrets em memória;
* prompt injection que leve a execução de ação sensível;
* execução de código arbitrário gerado por modelo sem validação;
* alteração de configuração sem consentimento;
* uso de rede ou envio de dados externos sem autorização explícita;
* falha de isolamento entre escopos de memória, projeto ou sessão;
* vazamento de dados via audit logs, runs, workflows ou arquivos exportados;
* dependência vulnerável com impacto prático no Argos.

## O Que Normalmente Não é Vulnerabilidade

Os seguintes casos geralmente não são tratados como vulnerabilidade de segurança, a menos que tenham impacto claro:

* erro visual ou mensagem incorreta sem impacto em segurança;
* comportamento inesperado sem exposição de dados ou execução indevida;
* falha em ambiente muito customizado sem reprodução;
* lentidão, timeout ou erro de modelo local sem impacto em dados ou permissões;
* sugestão insegura feita pelo modelo, desde que o Argos não execute a ação sem validação/policy;
* problemas em forks modificados que não existem no repositório oficial.

Esses casos podem ser reportados como bug comum usando o template de issue apropriado.

## Expectativa de Resposta

O mantenedor tentará responder reportes de segurança o mais rápido possível.

Fluxo esperado:

1. Recebimento do reporte.
2. Análise inicial do impacto.
3. Tentativa de reprodução.
4. Classificação da severidade.
5. Planejamento da correção.
6. Correção e validação.
7. Publicação da correção.
8. Divulgação responsável, quando aplicável.

Como o projeto pode estar em fase inicial e mantido por poucas pessoas, os tempos de resposta podem variar. Mesmo assim, reportes de segurança terão prioridade sobre melhorias comuns.

## Classificação de Severidade

A severidade será avaliada considerando impacto, facilidade de exploração e área afetada.

### Crítica

Exemplos:

* execução remota ou local de comando sem confirmação;
* remoção ou alteração de arquivos do usuário sem autorização;
* exposição de credenciais;
* bypass claro de policy;
* workflow/tool executando ação destrutiva automaticamente.

### Alta

Exemplos:

* vazamento de dados sensíveis em logs, memória ou auditoria;
* acesso indevido a arquivos fora do escopo permitido;
* persistência indevida de dados sensíveis;
* falha que permite uso de tool com permissão excessiva.

### Média

Exemplos:

* falha de validação que pode levar a comportamento inseguro em cenário específico;
* erro de escopo em memória ou contexto sem vazamento crítico;
* configuração insegura por padrão, mas sem exploração direta comprovada.

### Baixa

Exemplos:

* mensagem confusa sobre permissões;
* log excessivamente detalhado sem dado sensível;
* comportamento inconsistente sem impacto direto em segurança.

## Diretrizes para Correções de Segurança

Correções de segurança devem seguir os princípios do Argos:

> Semântico para buscar, sugerir e contextualizar. Determinístico para validar, autorizar e executar.

Isso significa:

* o modelo pode sugerir ações, mas não deve autorizar execução sensível;
* policies devem ser aplicadas por código determinístico;
* ações sensíveis devem exigir confirmação quando necessário;
* logs e auditoria não devem expor secrets;
* workflows gerados por modelo devem nascer como draft;
* tools devem declarar permissões;
* memória deve bloquear credenciais e dados sensíveis;
* alterações de segurança devem ser testáveis.

## Segurança em Tools

Contribuições relacionadas a tools devem garantir que:

* permissões necessárias estejam documentadas;
* entradas sejam validadas;
* comandos perigosos sejam bloqueados;
* ações com efeito colateral exijam confirmação;
* dados sensíveis não sejam logados;
* erros não exponham secrets;
* a tool não colete ou envie dados sem consentimento.

Tools não devem executar comandos arbitrários sem validação explícita.

## Segurança em Workflows

Workflows devem ser declarativos, validáveis e auditáveis.

Regras esperadas:

* workflows gerados por modelo não são executados diretamente;
* workflows começam como `draft`;
* execução exige validação;
* habilitação exige aprovação;
* ações sensíveis exigem confirmação;
* todo run relevante deve gerar audit log;
* budgets e limites devem evitar loops infinitos;
* falhas devem passar pelo Recovery Harness quando aplicável.

Lifecycle esperado:

```text
draft -> validated -> approved -> enabled
```

## Segurança em Memória

O Argos não deve salvar automaticamente informações sensíveis.

Devem ser bloqueados:

* senhas;
* tokens;
* API keys;
* private keys;
* secrets;
* credenciais;
* dados pessoais sensíveis sem consentimento claro.

Memórias importantes, decisões de projeto, preferências globais e correções relevantes devem passar por confirmação quando configurado.

## Segurança em Logs e Auditoria

Logs, runs e audit logs devem evitar exposição de dados sensíveis.

Não devem aparecer em logs:

* senhas;
* tokens;
* secrets;
* private keys;
* credenciais;
* conteúdo sensível de arquivos;
* dados pessoais sem necessidade.

Quando necessário, use mascaramento:

```text
token=***REDACTED***
password=***REDACTED***
secret=***REDACTED***
```

## Dependências

Vulnerabilidades em dependências devem ser reportadas quando tiverem impacto no Argos.

Ao atualizar dependências por segurança, informe:

* dependência afetada;
* versão vulnerável;
* versão corrigida;
* impacto no projeto;
* testes executados.

## Divulgação Responsável

Pedimos que vulnerabilidades não sejam divulgadas publicamente antes de uma correção estar disponível ou antes de alinhamento com os mantenedores.

Quando a vulnerabilidade for confirmada, o projeto poderá publicar:

* descrição resumida;
* impacto;
* versões afetadas;
* versão corrigida;
* mitigação temporária, se houver;
* agradecimento ao responsável pelo reporte, se autorizado.

## Agradecimentos

Agradecemos a qualquer pessoa que reporte vulnerabilidades de forma responsável e ajude a tornar o Argos mais seguro.

Contribuições de segurança são especialmente importantes para o projeto, pois o Argos tem como objetivo executar automações locais com controle, transparência, privacidade e confiança.
