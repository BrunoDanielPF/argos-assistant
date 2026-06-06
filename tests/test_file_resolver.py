from assistant.files.resolver import FileResolver


def test_file_resolver_matches_name_without_extension(tmp_path):
    target = tmp_path / "hello_world.md"
    target.write_text("hello", encoding="utf-8")

    resolution = FileResolver().resolve("hello_world", [tmp_path])

    assert resolution.status == "resolved"
    assert resolution.matches == [str(target)]


def test_file_resolver_matches_typo_when_candidate_is_unambiguous(tmp_path):
    target = tmp_path / "hello_world.md"
    target.write_text("hello", encoding="utf-8")

    resolution = FileResolver().resolve("helo_world", [tmp_path])

    assert resolution.status == "resolved"
    assert resolution.matches == [str(target)]


def test_file_resolver_reports_ambiguous_extensions(tmp_path):
    markdown = tmp_path / "hello_world.md"
    text = tmp_path / "hello_world.txt"
    markdown.write_text("markdown", encoding="utf-8")
    text.write_text("text", encoding="utf-8")

    resolution = FileResolver().resolve("hello_world", [tmp_path])

    assert resolution.status == "ambiguous"
    assert set(resolution.matches) == {str(markdown), str(text)}


def test_file_resolver_reports_not_found(tmp_path):
    resolution = FileResolver().resolve("arquivo_inexistente", [tmp_path])

    assert resolution.status == "not_found"
    assert resolution.matches == []


def test_file_resolver_checks_direct_candidates_before_recursive_scan(tmp_path):
    first_root = tmp_path / "workspace"
    second_root = tmp_path / "home"
    first_root.mkdir()
    second_root.mkdir()
    (first_root / "decoy.txt").write_text("decoy", encoding="utf-8")
    target = second_root / "hello_world.md"
    target.write_text("hello", encoding="utf-8")

    resolution = FileResolver(max_scanned_files=1).resolve(
        "hello_world",
        [first_root, second_root],
    )

    assert resolution.status == "resolved"
    assert resolution.matches == [str(target.resolve())]
