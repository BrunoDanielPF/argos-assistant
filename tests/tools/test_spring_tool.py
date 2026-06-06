import importlib.util
from pathlib import Path

from assistant.tools.manifest import load_tool_manifest
from assistant.tools.validator import ToolValidator


TOOL_DIR = (
    Path(__file__).parents[2]
    / "tools"
    / "local.spring.create_project"
)


def load_handler():
    spec = importlib.util.spec_from_file_location(
        "spring_project_tool",
        TOOL_DIR / "handler.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_spring_tool_manifest_is_valid():
    manifest = load_tool_manifest(TOOL_DIR)
    report = ToolValidator().validate(TOOL_DIR)

    assert manifest.name == "local.spring.create_project"
    assert report.ok is True


def test_spring_tool_creates_minimal_maven_project(tmp_path):
    result = load_handler().run(
        {
            "name": "pedidos-api",
            "directory": str(tmp_path),
            "java_version": 21,
            "build_tool": "maven",
            "group_id": "com.example",
        }
    )

    project = tmp_path / "pedidos-api"
    assert (project / "pom.xml").exists()
    assert (
        project
        / "src"
        / "main"
        / "java"
        / "com"
        / "example"
        / "pedidosapi"
        / "PedidosApiApplication.java"
    ).exists()
    assert result["project_path"] == str(project)


def test_spring_tool_refuses_non_empty_destination(tmp_path):
    destination = tmp_path / "pedidos-api"
    destination.mkdir()
    (destination / "existing.txt").write_text("existing", encoding="utf-8")

    try:
        load_handler().run(
            {
                "name": "pedidos-api",
                "directory": str(tmp_path),
                "java_version": 21,
                "build_tool": "maven",
                "group_id": "com.example",
            }
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("tool must refuse non-empty destination")
