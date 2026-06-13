from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Thread
from time import monotonic, sleep

import httpx


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _metadata_definition() -> dict:
    return {
        "name": "file.metadata.stat",
        "version": "1.0.0",
        "title": "File Metadata",
        "description": "Read creation and modification metadata for one file.",
        "input_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": ["path"],
            "properties": {"path": {"type": "string", "minLength": 1}},
        },
        "output_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [
                "path",
                "created_at",
                "modified_at",
                "platform",
                "created_at_reliable",
            ],
            "properties": {
                "path": {"type": "string"},
                "created_at": {"type": ["string", "null"]},
                "modified_at": {"type": "string"},
                "platform": {"type": "string"},
                "created_at_reliable": {"type": "boolean"},
                "explanation": {"type": "string"},
            },
        },
        "permissions": {
            "filesystem": {"read": ["${path}"], "write": []},
            "network": {"enabled": False, "hosts": []},
            "subprocess": {"executables": []},
        },
        "execution": {"timeout_seconds": 10, "max_output_bytes": 16384},
        "handler_body": (
            "import os\n"
            "import platform\n"
            "from datetime import datetime, timezone\n\n"
            "def run(arguments):\n"
            "    path = os.path.abspath(arguments['path'])\n"
            "    metadata = os.stat(path)\n"
            "    system = platform.system()\n"
            "    reliable = system == 'Windows' or hasattr(metadata, 'st_birthtime')\n"
            "    created = metadata.st_ctime if system == 'Windows' else "
            "getattr(metadata, 'st_birthtime', None)\n"
            "    return {\n"
            "        'path': path,\n"
            "        'created_at': datetime.fromtimestamp(created, timezone.utc).isoformat() "
            "if created is not None else None,\n"
            "        'modified_at': datetime.fromtimestamp(metadata.st_mtime, timezone.utc).isoformat(),\n"
            "        'platform': system,\n"
            "        'created_at_reliable': reliable,\n"
            "        'explanation': '' if reliable else "
            "'Reliable creation time is unavailable on this platform.',\n"
            "    }\n"
        ),
    }


def _blocked_definition(requested_capability: str) -> dict:
    payload = _metadata_definition()
    payload["name"] = (
        "local.generic.shell"
        if requested_capability == "shell.run"
        else "network.download.file"
    )
    if requested_capability == "shell.run":
        payload["permissions"]["subprocess"]["executables"] = ["cmd"]
        payload["handler_body"] = (
            "import subprocess\n\n"
            "def run(arguments):\n"
            "    return {'path': subprocess.run(arguments['command'])}\n"
        )
    else:
        payload["permissions"]["filesystem"]["write"] = ["${path}"]
        payload["permissions"]["network"] = {
            "enabled": True,
            "hosts": ["*"],
        }
    return payload


class FakeOllamaServer:
    def __init__(self) -> None:
        self.port = _free_port()
        self._server = None
        self._thread = None

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                content = outer._response_content(payload)
                body = json.dumps(
                    {"message": {"content": content}}
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format, *_args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    @staticmethod
    def _response_content(payload: dict) -> str:
        messages = payload.get("messages") or []
        user_content = str(messages[-1].get("content", "")) if messages else ""
        if isinstance(payload.get("format"), dict):
            try:
                requested = json.loads(user_content).get(
                    "requested_capability",
                    "",
                )
            except json.JSONDecodeError:
                requested = ""
            definition = (
                _metadata_definition()
                if requested == "file.metadata.stat"
                else _blocked_definition(requested)
            )
            return json.dumps(definition)
        normalized = user_content.casefold()
        if "qualquer comando shell" in normalized:
            return json.dumps(
                {
                    "mode": "action",
                    "capability": "shell.run",
                    "arguments": {"command": "arbitrary"},
                }
            )
        if "baixar dados da internet" in normalized:
            return json.dumps(
                {
                    "mode": "action",
                    "capability": "network.download_file",
                    "arguments": {
                        "url": "https://example.com/data",
                        "path": "download.txt",
                    },
                }
            )
        return json.dumps(
            {"mode": "answer", "content": "Resposta do fake Ollama."}
        )


class ArgosGatewayHarness:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.argos_home = self.root / "argos-home"
        self.lab = self.root / "lab"
        self.gateway_port = _free_port()
        self.ollama = FakeOllamaServer()
        self.process = None
        self.responses: list[httpx.Response] = []
        self.last_response: dict | None = None
        self.gateway_log = self.argos_home / "logs" / "gateway-harness.log"
        self.environment = self._build_environment()

    def start_gateway(self) -> None:
        self._create_lab()
        self.ollama.start()
        self.gateway_log.parent.mkdir(parents=True, exist_ok=True)
        log_stream = self.gateway_log.open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.integration.gateway_harness_server",
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=self.environment,
            stdin=subprocess.DEVNULL,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
        )
        log_stream.close()
        deadline = monotonic() + 30
        while monotonic() < deadline:
            try:
                response = self._request("GET", "/v1/health")
                if response.status_code == 200:
                    return
            except (OSError, httpx.HTTPError):
                pass
            if self.process.poll() is not None:
                raise AssertionError(self.read_gateway_logs())
            sleep(0.1)
        raise TimeoutError(self.read_gateway_logs())

    def stop_gateway(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.ollama.stop()

    def send_chat(self, message: str, *, session: str = "default") -> dict:
        response = self._request(
            "POST",
            "/v1/chat",
            json={
                "session_id": session,
                "content": message,
                "cwd": str(self.lab),
            },
        )
        self.responses.append(response)
        self.last_response = response.json()
        return self.last_response

    def approve_confirmation(self, decision) -> dict:
        assert self.last_response is not None
        workflow_id = self.last_response.get("workflow_id")
        if decision in {
            "approve_enable_only",
            "approve_enable_and_run_once",
            "reject",
            "cancel",
        }:
            path = (
                f"/v1/capability-workflows/{workflow_id}/tool-decision"
            )
            payload = {"decision": decision}
        elif decision in {"confirm", "retry_reject", "retry_cancel"}:
            mapped = {
                "confirm": "confirm",
                "retry_reject": "reject",
                "retry_cancel": "cancel",
            }[decision]
            path = (
                f"/v1/capability-workflows/{workflow_id}/retry-decision"
            )
            payload = {"decision": mapped}
        else:
            confirmation = self.last_response["confirmation"]
            path = (
                f"/v1/confirmations/{confirmation['confirmation_id']}"
            )
            payload = {"approved": bool(decision)}
        response = self._request("POST", path, json=payload)
        self.responses.append(response)
        self.last_response = response.json()
        return self.last_response

    def list_pending_workflows(
        self,
        *,
        session: str = "default",
    ) -> list[dict]:
        response = self._request(
            "GET",
            f"/v1/capability-workflows?session_id={session}",
        )
        self.responses.append(response)
        return response.json()["workflows"]

    def read_session(self, session: str = "default") -> dict:
        response = self._request("GET", f"/v1/sessions/{session}")
        self.responses.append(response)
        return response.json()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "from assistant.cli import app; app()",
                *arguments,
            ],
            cwd=Path(__file__).resolve().parents[2],
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def read_gateway_logs(self) -> str:
        if not self.gateway_log.exists():
            return ""
        return self.gateway_log.read_text(
            encoding="utf-8",
            errors="replace",
        )

    def assert_no_http_500(self) -> None:
        failures = [
            response
            for response in self.responses
            if response.status_code >= 500
        ]
        assert not failures, [
            (response.status_code, response.text)
            for response in failures
        ]

    def assert_no_traceback(self) -> None:
        logs = self.read_gateway_logs()
        assert "Traceback (most recent call last)" not in logs, logs
        assert "Exception in ASGI application" not in logs, logs

    def _request(self, method: str, path: str, json: dict | None = None):
        token_file = self.argos_home / "gateway.token"
        token = (
            token_file.read_text(encoding="ascii").strip()
            if token_file.exists()
            else "not-ready"
        )
        return httpx.request(
            method,
            f"http://127.0.0.1:{self.gateway_port}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=json,
            timeout=120,
        )

    def _create_lab(self) -> None:
        self.lab.mkdir(parents=True, exist_ok=True)
        (self.lab / "arquivo-a.txt").write_text("A", encoding="utf-8")
        (self.lab / "arquivo-b.txt").write_text("B", encoding="utf-8")
        (self.lab / "lixo.tmp").write_text("tmp", encoding="utf-8")
        (self.lab / "backup").mkdir()

    def _build_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        source_root = Path(__file__).resolve().parents[2]
        environment.update(
            {
                "ARGOS_HOME": str(self.argos_home),
                "ARGOS_GATEWAY_PORT": str(self.gateway_port),
                "ARGOS_OLLAMA_BASE_URL": (
                    f"http://127.0.0.1:{self.ollama.port}/api"
                ),
                "ARGOS_MODEL": "argos-harness",
                "PYTHONPATH": os.pathsep.join(
                    [
                        str(source_root),
                        str(source_root / "src"),
                        environment.get("PYTHONPATH", ""),
                    ]
                ),
            }
        )
        return environment
