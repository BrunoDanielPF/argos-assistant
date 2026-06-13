import unicodedata


class NoExecutionGuard:
    _markers = (
        "sem executar nada",
        "nao execute",
        "nao executar",
        "apenas explique",
        "somente explique",
        "so explique",
        "so me diga o plano",
        "apenas me diga o plano",
    )

    def blocks(self, user_input: str) -> bool:
        normalized = self._normalize(user_input)
        return any(marker in normalized for marker in self._markers)

    def conceptual_plan(self, user_input: str) -> str:
        normalized = self._normalize(user_input)
        if "mover" in normalized and "arquivo" in normalized:
            return (
                "Plano conceitual, sem executar nenhuma acao:\n"
                "1. Localizar os arquivos que correspondem ao padrao pedido.\n"
                "2. Validar ou criar a pasta de destino.\n"
                "3. Fazer um dry-run listando origem e destino de cada arquivo.\n"
                "4. Solicitar confirmacao antes de mover os arquivos."
            )
        return (
            "Plano conceitual, sem executar nenhuma acao:\n"
            "1. Identificar os dados e recursos envolvidos.\n"
            "2. Validar pre-condicoes e permissoes.\n"
            "3. Preparar um dry-run com o efeito esperado.\n"
            "4. Solicitar confirmacao antes de qualquer execucao."
        )

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value.casefold())
        return "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        )
