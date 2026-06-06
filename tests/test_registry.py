from assistant.capabilities.registry import build_default_registry


def test_registry_contains_mvp_capabilities():
    registry = build_default_registry()
    capability_names = {item.name for item in registry.list_all()}
    assert "open_application" in capability_names
    assert "open_url" in capability_names
    assert "search_files" in capability_names
    assert "create_file" in capability_names
