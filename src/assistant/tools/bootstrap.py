import importlib.util
import json
from pathlib import Path
import sys
import traceback


def main() -> int:
    entrypoint = Path(sys.argv[1])
    try:
        spec = importlib.util.spec_from_file_location("argos_dynamic_tool", entrypoint)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load tool entrypoint")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        request = json.loads(sys.stdin.read())
        result = module.run(request["arguments"])
        sys.stdout.write(json.dumps({"ok": True, "result": result, "error": None}))
        return 0
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        sys.stdout.write(
            json.dumps(
                {
                    "ok": False,
                    "result": None,
                    "error": {"code": "tool_error", "message": str(exc)},
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
