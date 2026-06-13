from assistant.capabilities.argument_resolver import CapabilityArgumentResolver


def test_resolver_preserves_explicit_arguments_and_binds_safe_context_fields():
    resolver = CapabilityArgumentResolver()

    resolved = resolver.resolve(
        "files.search",
        {"pattern": "*.txt", "max_results": 10},
        {
            "current_cwd": "C:/work",
            "default_search_root": "C:/fallback",
        },
    )

    assert resolved == {
        "root": "C:/work",
        "pattern": "*.txt",
        "max_results": 10,
    }


def test_resolver_never_synthesizes_sensitive_or_semantic_arguments():
    resolver = CapabilityArgumentResolver()

    resolved = resolver.resolve(
        "file.write",
        {"path": "notes.txt"},
        {
            "current_cwd": "C:/work",
            "content": "unsafe",
            "token": "secret",
            "value": "456",
        },
    )

    assert resolved == {"path": "notes.txt"}
