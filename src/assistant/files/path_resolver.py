from pathlib import Path


class PathResolver:
    _CURRENT_DIRECTORY_MARKERS = {
        ".",
        "aqui",
        "nesta pasta",
        "nessa pasta",
        "pasta atual",
        "diretorio atual",
        "diretório atual",
    }

    def resolve(self, value: str, context: dict) -> Path:
        normalized = value.strip().strip("\"'")
        if normalized.casefold() in self._CURRENT_DIRECTORY_MARKERS:
            return self._current_cwd(context)

        candidate = Path(normalized).expanduser()
        if not candidate.is_absolute():
            candidate = self._current_cwd(context) / candidate
        return candidate.resolve()

    @staticmethod
    def _current_cwd(context: dict) -> Path:
        value = context.get("current_cwd")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("current_cwd is required to resolve relative paths")
        return Path(value).expanduser().resolve()
