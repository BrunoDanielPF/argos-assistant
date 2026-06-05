# Memoria de Longo Prazo

Use esta skill ao planejar, criar ou revisar a memoria progressiva do Argos.

Objetivo:
- Transformar correcoes e preferencias do usuario em aprendizados reutilizaveis.
- Salvar aprendizados em arquivos Markdown pequenos, semanticos e versionaveis.
- Manter a memoria fora do repositorio por padrao, em uma pasta do usuario.

Padrao de armazenamento:
- Pasta base sugerida: `%USERPROFILE%\.argos\memory`.
- Usar arquivos `.md` por topico, por exemplo `preferencias.md`, `projetos.md`, `ferramentas.md`, `comandos.md` e `correcoes.md`.
- Cada memoria deve ter titulo, contexto, aprendizado, fonte e data.
- Nao salvar segredos, tokens, senhas, chaves privadas ou dados sensiveis.

Workflow:
- Detectar se o usuario corrigiu o Argos, declarou uma preferencia ou ensinou um procedimento recorrente.
- Confirmar antes de salvar memoria persistente.
- Resumir o aprendizado de forma curta e verificavel.
- Escolher o arquivo semantico mais adequado.
- Atualizar ou criar entrada Markdown sem duplicar informacao.

Formato recomendado:

```markdown
## <titulo curto>

- Data: YYYY-MM-DD
- Contexto: <onde isso se aplica>
- Aprendizado: <regra ou preferencia objetiva>
- Fonte: correcao do usuario
```

Saida esperada:
- Proposta do que sera lembrado.
- Arquivo de destino.
- Riscos de privacidade, se houver.
- Pedido de confirmacao antes de persistir.
