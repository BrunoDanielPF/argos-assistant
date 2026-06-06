from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import unicodedata


@dataclass(frozen=True)
class FileResolution:
    status: str
    matches: list[str]


class FileResolver:
    def __init__(self, max_scanned_files: int = 5000) -> None:
        self._max_scanned_files = max_scanned_files

    def resolve(self, query: str, roots: list[str | Path], max_results: int = 5) -> FileResolution:
        normalized_query = query.strip().strip("\"'")
        if not normalized_query:
            return FileResolution(status="not_found", matches=[])

        direct_path = Path(normalized_query).expanduser()
        if direct_path.is_file():
            return FileResolution(status="resolved", matches=[str(direct_path.resolve())])

        query_name = self._normalize(direct_path.name)
        query_stem = self._normalize(direct_path.stem)
        has_suffix = bool(direct_path.suffix)
        direct_matches: list[str] = []
        for root_value in roots:
            root = Path(root_value).expanduser()
            if not root.exists() or not root.is_dir():
                continue
            exact_candidate = root / direct_path.name
            if exact_candidate.is_file():
                direct_matches.append(str(exact_candidate.resolve()))
            if not has_suffix:
                try:
                    direct_matches.extend(
                        str(candidate.resolve())
                        for candidate in root.glob(f"{direct_path.name}.*")
                        if candidate.is_file()
                    )
                except (OSError, PermissionError):
                    continue
        unique_direct_matches = sorted(set(direct_matches), key=str.lower)
        if len(unique_direct_matches) == 1:
            return FileResolution(status="resolved", matches=unique_direct_matches)
        if len(unique_direct_matches) > 1:
            return FileResolution(
                status="ambiguous",
                matches=unique_direct_matches[:max_results],
            )

        scored: list[tuple[float, str]] = []
        seen: set[str] = set()
        scanned = 0

        for root_value in roots:
            root = Path(root_value).expanduser()
            if not root.exists() or not root.is_dir():
                continue
            try:
                candidates = root.rglob("*")
                for candidate in candidates:
                    if scanned >= self._max_scanned_files:
                        break
                    if not candidate.is_file():
                        continue
                    scanned += 1
                    resolved = str(candidate.resolve())
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    score = self._score(query_name, query_stem, has_suffix, candidate)
                    if score >= 0.60:
                        scored.append((score, resolved))
            except (OSError, PermissionError):
                continue
            if scanned >= self._max_scanned_files:
                break

        scored.sort(key=lambda item: (-item[0], item[1].lower()))
        visible = scored[:max_results]
        if not visible:
            return FileResolution(status="not_found", matches=[])

        top_score = visible[0][0]
        top_matches = [path for score, path in visible if abs(score - top_score) < 0.02]
        if len(top_matches) == 1:
            second_score = visible[1][0] if len(visible) > 1 else 0.0
            if top_score >= 0.82 and top_score - second_score >= 0.08:
                return FileResolution(status="resolved", matches=top_matches)

        return FileResolution(
            status="ambiguous",
            matches=[path for _, path in visible],
        )

    def _score(
        self,
        query_name: str,
        query_stem: str,
        has_suffix: bool,
        candidate: Path,
    ) -> float:
        candidate_name = self._normalize(candidate.name)
        candidate_stem = self._normalize(candidate.stem)
        if query_name == candidate_name:
            return 1.0
        if not has_suffix and query_stem == candidate_stem:
            return 0.98
        name_ratio = SequenceMatcher(None, query_name, candidate_name).ratio()
        stem_ratio = SequenceMatcher(None, query_stem, candidate_stem).ratio()
        if query_stem and query_stem in candidate_stem:
            stem_ratio = max(stem_ratio, 0.90)
        return max(name_ratio, stem_ratio)

    def _normalize(self, value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()
