from pathlib import Path

from assistant.capabilities.registry import build_default_registry
from assistant.tools.catalog import ToolCatalog
from assistant.tools.state import ToolStateStore


REPO_ROOT = Path(__file__).parents[2]


def bundled_catalog(tmp_path):
    return ToolCatalog(
        tools_root=tmp_path / "user-tools",
        state_store=ToolStateStore(tmp_path / "state.json"),
        bundled_root=REPO_ROOT / "tools",
    )


def test_catalog_does_not_expose_specific_development_templates_by_default(tmp_path):
    catalog = bundled_catalog(tmp_path)

    assert catalog.get_enabled("local.spring.create_project") is None


def test_registry_does_not_include_specific_development_templates_by_default(tmp_path):
    registry = build_default_registry(bundled_catalog(tmp_path))

    assert registry.get("local.spring.create_project") is None
