# Resolucao de Arquivos e Clarificacao Semantica

## Objetivo

Permitir que o Argos localize arquivos por nome parcial ou aproximado e solicite detalhes quando uma operacao permanecer ambigua, mantendo a conversa natural e impedindo alteracoes incorretas.

## Principios

- O modelo nao deve tratar um nome incompleto como caminho literal.
- O Argos nao deve inventar extensao, arquivo ou modo de escrita.
- Numeros nas opcoes sao atalhos, nao respostas obrigatorias.
- Respostas como `substituir`, `pode sobrescrever`, `adicione no final` e equivalentes devem ser interpretadas no contexto da pergunta pendente.
- Escritas exigem arquivo resolvido, modo definido e confirmacao.
- Confianca insuficiente gera nova pergunta, nunca execucao.

## Arquitetura

O `Planner` reconhece pedidos de edicao e retorna `mode=clarification` quando faltar o modo de escrita. A `SessionMemory` armazena a pergunta e a operacao pendente. Na mensagem seguinte, o planner resolve primeiro numeros e sinonimos conhecidos e usa o modelo local como fallback semantico restrito as opcoes disponiveis.

Antes da politica de execucao, o `AssistantAgent` usa um `FileResolver`. O resolvedor procura em `current_cwd` e `user_home`, compara nome completo e stem, aceita extensoes omitidas e calcula similaridade para erros de digitacao. Um candidato inequivoco segue para confirmacao; varios candidatos geram uma clarificacao de selecao; nenhum candidato gera uma pergunta sobre novo local ou criacao.

A capability `write_file` implementa apenas duas operacoes explicitas:

- `replace`: substitui o conteudo completo;
- `append`: adiciona o texto ao final preservando o conteudo existente.

## Contratos

Clarificacao:

```json
{
  "mode": "clarification",
  "question": "Voce quer substituir o conteudo ou adicionar ao final?",
  "pending": {
    "kind": "action_argument",
    "field": "write_mode",
    "action": {
      "capability": "write_file",
      "arguments": {
        "path": "hello_world",
        "content": "ola mundo bruno"
      }
    },
    "options": [
      {"id": "replace", "label": "substituir"},
      {"id": "append", "label": "adicionar ao final"},
      {"id": "cancel", "label": "cancelar"}
    ]
  }
}
```

Resolucao de arquivo:

- `resolved`: um candidato com alta confianca;
- `ambiguous`: mais de um candidato plausivel;
- `not_found`: nenhum candidato plausivel.

## Fluxo

1. O usuario solicita uma edicao.
2. O planner extrai referencia e conteudo.
3. Se o modo estiver ausente, o Argos pergunta.
4. A resposta natural completa o plano pendente.
5. O agente resolve o arquivo por similaridade.
6. Se houver duvida, o Argos pergunta qual arquivo usar.
7. A politica mostra o caminho resolvido e pede confirmacao.
8. O executor escreve e valida o resultado.

## Seguranca

- `write_file` permanece na politica `confirm`.
- O caminho final deve apontar para um arquivo existente.
- Criacao de arquivo continua sendo uma capability separada.
- Cancelamento limpa a operacao pendente.
- O modelo nao pode selecionar opcoes fora da lista fornecida.

## Testes

- pedido de edicao sem modo retorna clarificacao;
- respostas numericas, sinonimos e frases naturais resolvem a mesma opcao;
- resposta incerta repete a clarificacao;
- nome sem extensao resolve `hello_world.md`;
- erro de digitacao resolve candidato inequivoco;
- multiplos candidatos pedem selecao;
- nenhum candidato nao cria arquivo automaticamente;
- escrita substitui ou adiciona somente apos confirmacao.
