from assistant.execution.executor import ActionExecutor
from assistant.jobs.repository import JobRepository


def test_executor_opens_url_with_launcher(monkeypatch):
    launched = {}

    def fake_open(url: str) -> None:
        launched["url"] = url

    executor = ActionExecutor(open_url_fn=fake_open)
    result = executor.execute("open_url", {"url": "https://example.com"})

    assert result.ok is True
    assert launched["url"] == "https://example.com"


def test_executor_opens_application_with_launcher():
    launched = {}

    def fake_open_application(application: str) -> None:
        launched["application"] = application

    executor = ActionExecutor(open_application_fn=fake_open_application)
    result = executor.execute("open_application", {"application": "notepad"})

    assert result.ok is True
    assert launched["application"] == "notepad.exe"


def test_executor_normalizes_known_application_alias():
    launched = {}

    def fake_open_application(application: str) -> None:
        launched["application"] = application

    executor = ActionExecutor(open_application_fn=fake_open_application)
    result = executor.execute("open_application", {"application": "calculator"})

    assert result.ok is True
    assert launched["application"] == "calc.exe"


def test_executor_opens_file_with_launcher(tmp_path):
    launched = {}
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")

    def fake_open_file(path: str) -> None:
        launched["path"] = path

    executor = ActionExecutor(open_file_fn=fake_open_file)
    result = executor.execute("open_file", {"path": str(target)})

    assert result.ok is True
    assert launched["path"] == str(target)


def test_executor_reports_missing_file_for_open_file(tmp_path):
    executor = ActionExecutor(open_file_fn=lambda path: None)
    missing = tmp_path / "missing.txt"

    result = executor.execute("open_file", {"path": str(missing)})

    assert result.ok is False
    assert "File not found" in result.message


def test_executor_creates_file_with_content(tmp_path):
    target = tmp_path / "hello_world.md"
    executor = ActionExecutor(open_file_fn=lambda path: None)

    result = executor.execute(
        "create_file",
        {"path": str(target), "content": "hello world"},
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "hello world"
    assert "Created file" in result.message


def test_executor_create_file_creates_parent_directories(tmp_path):
    target = tmp_path / "docs" / "hello_world.md"
    executor = ActionExecutor(open_file_fn=lambda path: None)

    result = executor.execute(
        "create_file",
        {"path": str(target), "content": "hello world"},
    )

    assert result.ok is True
    assert target.exists()


def test_executor_searches_files(monkeypatch, tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    executor = ActionExecutor()

    result = executor.execute(
        "search_files",
        {"root": str(tmp_path), "pattern": "notes.txt"},
    )

    assert result.ok is True
    assert "Found 1 match" in result.message
    assert "notes.txt" in result.message
    assert result.data == {"matches": [str(target)], "all_count": 1}


def test_executor_limits_search_results(tmp_path):
    for index in range(3):
        target = tmp_path / f"notes-{index}.txt"
        target.write_text("hello", encoding="utf-8")

    executor = ActionExecutor()
    result = executor.execute(
        "search_files",
        {"root": str(tmp_path), "pattern": "notes-*.txt", "max_results": 2},
    )

    assert result.ok is True
    assert "Found 3 matches" in result.message
    assert "Showing first 2." in result.message
    assert len(result.data["matches"]) == 2


def test_executor_reports_search_files_no_matches(tmp_path):
    executor = ActionExecutor()
    result = executor.execute(
        "search_files",
        {"root": str(tmp_path), "pattern": "missing.txt"},
    )

    assert result.ok is False
    assert "No files matched" in result.message


def test_executor_replaces_existing_file_content(tmp_path):
    target = tmp_path / "hello_world.md"
    target.write_text("hello world", encoding="utf-8")

    result = ActionExecutor().execute(
        "write_file",
        {"path": str(target), "content": "ola mundo bruno", "write_mode": "replace"},
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "ola mundo bruno"


def test_executor_appends_to_existing_file_content(tmp_path):
    target = tmp_path / "hello_world.md"
    target.write_text("hello world", encoding="utf-8")

    result = ActionExecutor().execute(
        "write_file",
        {"path": str(target), "content": "ola mundo bruno", "write_mode": "append"},
    )

    assert result.ok is True
    assert target.read_text(encoding="utf-8") == "hello world\nola mundo bruno"


def test_executor_write_file_rejects_missing_file(tmp_path):
    target = tmp_path / "missing.md"

    result = ActionExecutor().execute(
        "write_file",
        {"path": str(target), "content": "texto", "write_mode": "replace"},
    )

    assert result.ok is False
    assert not target.exists()


def test_executor_write_file_rejects_unknown_mode(tmp_path):
    target = tmp_path / "hello_world.md"
    target.write_text("hello", encoding="utf-8")

    result = ActionExecutor().execute(
        "write_file",
        {"path": str(target), "content": "texto", "write_mode": "maybe"},
    )

    assert result.ok is False
    assert target.read_text(encoding="utf-8") == "hello"


def test_executor_schedules_reminder_job(tmp_path):
    repository = JobRepository(tmp_path / "argos.db")

    result = ActionExecutor(job_repository=repository).execute(
        "schedule_reminder",
        {
            "session_id": "s1",
            "content": "revisar documento",
            "scheduled_for": "2026-06-07T12:00:00+00:00",
        },
    )

    assert result.ok is True
    job = repository.load(result.data["job_id"])
    assert job is not None
    assert job.session_id == "s1"
    assert job.payload == {
        "type": "reminder",
        "content": "Lembrete: revisar documento",
    }
    assert job.scheduled_for.isoformat() == "2026-06-07T12:00:00+00:00"
    repository.close()


def test_executor_rejects_reminder_without_repository():
    result = ActionExecutor().execute(
        "schedule_reminder",
        {
            "content": "revisar documento",
            "scheduled_for": "2026-06-07T12:00:00+00:00",
        },
    )

    assert result.ok is False
    assert "not configured" in result.message
