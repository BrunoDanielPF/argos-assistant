from pathlib import Path
from collections.abc import Mapping

import yaml


def load_skills(skills_root: Path) -> list[dict]:
    skills = []
    if not skills_root.exists():
        return skills

    for skill_file in skills_root.glob("*/skill.yaml"):
        payload = yaml.safe_load(skill_file.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError(
                f"Invalid skill metadata in {skill_file}: expected a mapping, "
                f"got {type(payload).__name__}"
            )

        skill = dict(payload)
        skill["path"] = str(skill_file.parent)
        skills.append(skill)
    return skills
