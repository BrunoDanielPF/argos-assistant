from pathlib import Path
import importlib.util


def test_handler_creates_project(tmp_path):
    handler_path = Path(__file__).parents[1] / "handler.py"
    spec = importlib.util.spec_from_file_location("spring_tool", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.run(
        {
            "name": "demo-api",
            "directory": str(tmp_path),
            "java_version": 21,
            "build_tool": "maven",
            "group_id": "com.example",
        }
    )

    assert Path(result["project_path"]).exists()
