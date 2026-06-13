from __future__ import annotations

import re
from pathlib import Path


class DeterministicIntentRouter:
    def route(
        self,
        user_input: str,
        context: dict,
    ) -> dict | None:
        source = user_input.strip()

        shell = self._route_shell(source)
        if shell is not None:
            return shell

        environment_path = self._route_environment_path(source)
        if environment_path is not None:
            return environment_path

        return self._route_file(source, context)

    @staticmethod
    def _route_shell(normalized: str) -> dict | None:
        match = re.fullmatch(
            r"(?:"
            r"(?:rode|execute|executar)\s+(?:o\s+)?comando\s+"
            r"|no\s+terminal\s+(?:rode|execute|executar)\s+"
            r")(.+)",
            normalized,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None
        command = match.group(1).strip()
        return {
            "mode": "action",
            "capability": "shell.run",
            "arguments": {"command": command},
        }

    @staticmethod
    def _route_environment_path(normalized: str) -> dict | None:
        match = re.fullmatch(
            r"(?:adicione|adicionar|altere|alterar)\s+(.+?)\s+"
            r"(?:ao|a)\s+(?:vari[aá]vel\s+(?:de\s+ambiente\s+)?path|"
            r"path(?:\s+do\s+windows)?)"
            r"(?:\s+do\s+(usu[aá]rio|sistema))?",
            normalized,
            flags=re.IGNORECASE,
        )
        if match is None:
            match = re.fullmatch(
                r"(?:adicione|adicionar)\s+(?:ao|a)\s+"
                r"(?:vari[aá]vel\s+(?:de\s+ambiente\s+)?path|"
                r"path(?:\s+do\s+windows)?)\s+(.+)",
                normalized,
                flags=re.IGNORECASE,
            )
            if match is None:
                return None
            value = match.group(1)
            scope = "user"
        else:
            value = match.group(1)
            scope = (
                "system"
                if match.group(2)
                and match.group(2).casefold() == "sistema"
                else "user"
            )
        return {
            "mode": "action",
            "capability": "modify_path",
            "arguments": {
                "value": value.strip().strip('"'),
                "scope": scope,
            },
        }

    def _route_file(self, normalized: str, context: dict) -> dict | None:
        create_directory = re.fullmatch(
            r"(?:crie|criar)\s+uma\s+pasta\s+"
            r"(?:chamada\s+)?([a-z0-9_.-]+)",
            normalized,
            flags=re.IGNORECASE,
        )
        if create_directory:
            return self._action(
                "file.create_directory",
                {"path": create_directory.group(1)},
            )

        create_file = re.fullmatch(
            r"(?:crie|criar)\s+um\s+arquivo\s+"
            r"(?:chamado\s+)?([a-z0-9_.-]+\.[a-z0-9]+)",
            normalized,
            flags=re.IGNORECASE,
        )
        if create_file:
            root = self._operational_root(context) or "."
            return self._action(
                "create_file",
                {
                    "path": str(Path(root) / create_file.group(1)),
                    "content": "",
                },
            )

        read_file = re.fullmatch(
            r"(?:leia|ler)\s+(?:o\s+)?arquivo\s+(.+)",
            normalized,
            flags=re.IGNORECASE,
        )
        if read_file:
            return self._action(
                "file.read",
                {"path": self._clean_value(read_file.group(1))},
            )

        open_file = re.fullmatch(
            r"(?:abra|abrir)\s+(?:o\s+)?arquivo\s+(.+)",
            normalized,
            flags=re.IGNORECASE,
        )
        if open_file:
            return self._action(
                "file.open",
                {"path": self._clean_value(open_file.group(1))},
            )

        search = re.fullmatch(
            r"(?:buscar|busque|procure|liste|listar|mostre|"
            r"quais(?:\s+s[aã]o)?)(?:\s+os)?\s+arquivos?\s+"
            r"(\*?\.[a-z0-9]+|[a-z0-9]+)"
            r"(?:\s+(?:existem?\s+)?"
            r"(?:nesta\s+pasta|nessa\s+pasta|aqui|"
            r"(?:na\s+)?pasta\s+atual))?",
            normalized,
            flags=re.IGNORECASE,
        )
        if search:
            suffix = search.group(1)
            pattern = (
                suffix
                if suffix.startswith("*.")
                else f"*.{suffix.lstrip('.')}"
            )
            root = self._operational_root(context)
            arguments = {"pattern": pattern, "max_results": 5}
            if root is not None:
                arguments["root"] = root
            return self._action("files.search", arguments)

        simulated_delete = re.search(
            r"(?:dry[- ]run|simule|simular).+?"
            r"(?:apagar|apague|excluir|delete).+?"
            r"(\*\.[a-z0-9]+|\.[a-z0-9]+)",
            normalized,
            flags=re.IGNORECASE,
        )
        if simulated_delete:
            pattern = simulated_delete.group(1)
            if pattern.startswith("."):
                pattern = f"*{pattern}"
            return self._action(
                "file.delete_dry_run",
                {
                    "path": self._operational_root(context) or ".",
                    "pattern": pattern,
                },
            )

        delete_one = re.fullmatch(
            r"(?:apague|apagar|exclua|excluir|delete)\s+"
            r"(?:o\s+)?arquivo\s+(.+)",
            normalized,
            flags=re.IGNORECASE,
        )
        if delete_one:
            return self._action(
                "file.delete_one",
                {
                    "path": self._clean_value(delete_one.group(1)),
                    "recursive": False,
                },
            )

        move_files = re.fullmatch(
            r"(?:mova|mover)\s+(?:(?:todos\s+)?os\s+)?arquivos?"
            r"(?:\s+(\*\.[a-z0-9]+|\.[a-z0-9]+|[a-z0-9]+))?"
            r"\s+para\s+(?:(?:uma|a)\s+)?pasta\s+(.+)",
            normalized,
            flags=re.IGNORECASE,
        )
        if move_files:
            requested_pattern = move_files.group(1)
            if requested_pattern is None:
                pattern = "*"
            elif requested_pattern.startswith("*."):
                pattern = requested_pattern
            elif requested_pattern.startswith("."):
                pattern = f"*{requested_pattern}"
            else:
                pattern = f"*.{requested_pattern}"
            arguments = {
                "pattern": pattern,
                "destination": self._clean_value(move_files.group(2)),
            }
            root = self._operational_root(context)
            if root is not None:
                arguments["source_root"] = root
            return self._action("file.move_many", arguments)

        return None

    @staticmethod
    def _action(capability: str, arguments: dict) -> dict:
        return {
            "mode": "action",
            "capability": capability,
            "arguments": arguments,
        }

    @staticmethod
    def _operational_root(context: dict) -> str | None:
        for key in ("current_cwd", "default_search_root"):
            value = context.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _clean_value(value: str) -> str:
        return value.strip().strip("\"'")
