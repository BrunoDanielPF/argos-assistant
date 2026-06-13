from __future__ import annotations

import json
import os
from pathlib import Path

import uvicorn

import assistant.runtime.factory as factory_module
from assistant.config import AppConfig
from assistant.gateway.app import create_gateway_app
from assistant.gateway.auth import LocalTokenStore
from assistant.gateway.service import GatewayService
from assistant.observability.events import EventLog
from assistant.runtime.factory import RuntimeFactory
from assistant.sessions.repository import SessionRepository
from assistant.tools.runner import ToolRunResult, ToolRunner


class HarnessToolRunner(ToolRunner):
    def run(self, tool, arguments):
        if tool.manifest.name != "local.windows.env_set_user":
            return super().run(tool, arguments)
        log_file = Path(os.environ["ARGOS_HOME"]) / "logs" / "fake-runner.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "tool": tool.manifest.name,
                        "arguments": arguments,
                    },
                    ensure_ascii=True,
                )
                + "\n"
            )
        return ToolRunResult(
            ok=True,
            result={
                "name": arguments["name"],
                "scope": "user",
                "updated": True,
            },
        )


def main() -> None:
    factory_module.ToolRunner = HarnessToolRunner
    config = AppConfig.load()
    token_store = LocalTokenStore(config.gateway_token_file)
    token_store.get_or_create()
    repository = SessionRepository(config.database_file)
    service = GatewayService(
        RuntimeFactory(config),
        repository,
        event_log=EventLog(config.event_log_file),
    )
    app = create_gateway_app(
        service=service,
        token_store=token_store,
        repository=repository,
        model_name=config.model,
    )
    uvicorn.run(
        app,
        host=config.gateway_host,
        port=config.gateway_port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
