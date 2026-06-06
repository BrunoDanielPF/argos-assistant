import re
from pathlib import Path

import pytest

from assistant.skills.loader import load_skills


def test_load_skills_reads_yaml_metadata(tmp_path):
    skill_dir = tmp_path / "skills" / "sample"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "skill.yaml"
    skill_file.write_text(
        "name: sample\n"
        "description: Sample skill\n"
        "triggers:\n"
        "  - summarize\n",
        encoding="utf-8",
    )

    skills = load_skills(tmp_path / "skills")

    assert len(skills) == 1
    assert skills[0]["name"] == "sample"
    assert skills[0]["description"] == "Sample skill"
    assert skills[0]["triggers"] == ["summarize"]
    assert skills[0]["path"] == str(skill_dir)


def test_load_skills_rejects_empty_yaml_payload(tmp_path):
    skill_dir = tmp_path / "skills" / "sample"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "skill.yaml"
    skill_file.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match=re.escape(str(skill_file))):
        load_skills(tmp_path / "skills")


def test_argos_project_skills_catalog_is_loadable():
    skills_root = Path(__file__).resolve().parents[1] / "skills"
    skills = load_skills(skills_root)
    by_name = {skill["name"]: skill for skill in skills}
    expected_names = {
        "project-architecture",
        "mcp-server-creation",
        "test-generation",
        "internal-prompt-creation",
        "dataset-generation",
        "dataset-curation",
        "model-benchmarking",
        "performance-profiling",
        "configuration-management",
        "local-setup",
        "cli-command-generation",
        "project-security",
        "command-simulation",
        "documentation-maintenance",
        "long-term-memory",
        "workflow-orchestration",
    }

    assert expected_names.issubset(by_name)
    for skill_name in expected_names:
        skill = by_name[skill_name]
        assert skill["permission_profile"] == "advisory"
        assert skill["triggers"]
        prompt_path = Path(skill["path"]) / skill["instructions_file"]
        assert prompt_path.exists()
