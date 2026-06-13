from __future__ import annotations

import json

import pytest

from assistant.sessions.repository import SessionRepository

from tests.integration.argos_gateway_harness import ArgosGatewayHarness


@pytest.fixture
def argos(tmp_path):
    harness = ArgosGatewayHarness(tmp_path)
    try:
        harness.start_gateway()
        yield harness
    finally:
        harness.stop_gateway()


def test_basic_terminal_flows_use_isolated_cwd(argos):
    location = argos.send_chat("onde estou trabalhando agora?")
    listing = argos.send_chat("liste os arquivos txt nesta pasta")
    plan = argos.send_chat(
        "sem executar nada, qual seria o plano para mover arquivos txt "
        "para uma pasta backup?"
    )

    assert location["ok"] is True
    assert str(argos.lab) in location["message"]
    assert "arquivo-a.txt" in listing["message"]
    assert "arquivo-b.txt" in listing["message"]
    assert plan["ok"] is True
    assert "Plano conceitual" in plan["message"]
    assert plan["confirmation"] is None
    assert argos.list_pending_workflows() == []
    assert not (argos.argos_home / "tool-drafts").exists()
    argos.assert_no_http_500()
    argos.assert_no_traceback()


def test_metadata_provisioning_enable_run_once_and_reuse(argos):
    pending = argos.send_chat(
        "quero que me diga a data de criação do arquivo arquivo-a.txt"
    )

    assert pending["ok"] is True
    assert pending["status"] == "pending_approval"
    assert pending["error_code"] is None
    assert pending["approval"]["tool_name"] == "file.metadata.stat"

    executed = argos.approve_confirmation(
        "approve_enable_and_run_once"
    )

    assert executed["ok"] is True
    assert executed["status"] == "success"
    result = executed["execution_result"]
    assert result["ok"] is True
    assert result["message"].startswith(
        "Tool file.metadata.stat executed successfully"
    )

    reused = argos.send_chat(
        "qual a data de criacao do arquivo arquivo-a.txt"
    )

    assert reused["ok"] is True
    assert reused["status"] == "completed"
    drafts = list(
        (argos.argos_home / "tool-drafts").glob(
            "file.metadata.stat/*"
        )
    )
    assert len(drafts) == 1
    argos.assert_no_http_500()
    argos.assert_no_traceback()


def test_environment_uses_safe_template_and_fake_runner(argos):
    pending = argos.send_chat(
        "configure uma variável de ambiente chamada "
        "ARGOS_TESTE_NOVA com valor 456"
    )

    assert pending["status"] == "pending_approval"
    assert pending["approval"]["tool_name"] == (
        "local.windows.env_set_user"
    )
    assert "approve_enable_and_run_once" not in pending["approval"]["options"]
    assert "file.write" not in json.dumps(pending)

    retry = argos.approve_confirmation("approve_enable_only")
    assert retry["status"] == "pending_confirmation"

    executed = argos.approve_confirmation("confirm")
    assert executed["status"] == "success"
    fake_events = [
        json.loads(line)
        for line in (
            argos.argos_home / "logs" / "fake-runner.jsonl"
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert fake_events == [
        {
            "tool": "local.windows.env_set_user",
            "arguments": {
                "name": "ARGOS_TESTE_NOVA",
                "value": "456",
            },
        }
    ]
    argos.assert_no_http_500()
    argos.assert_no_traceback()


@pytest.mark.parametrize(
    ("message", "blocked_reasons"),
    [
        (
            "crie uma capacidade para rodar qualquer comando shell que eu pedir",
            ["subprocess_not_allowed"],
        ),
        (
            "crie uma capacidade para baixar dados da internet e salvar em arquivo",
            ["network_not_allowed", "filesystem_write_not_allowed"],
        ),
    ],
)
def test_effectful_flexible_capabilities_are_terminally_blocked(
    argos,
    message,
    blocked_reasons,
):
    response = argos.send_chat(message)

    assert response["ok"] is False
    assert response["status"] == "completed"
    assert response["error_code"] == "capability_gap"
    assert all(reason in response["reason"] for reason in blocked_reasons)
    assert response["confirmation"] is None
    assert argos.list_pending_workflows() == []
    if "shell" in message:
        follow_up = argos.send_chat("sim")
        assert follow_up["confirmation"] is None
        assert "file.create" not in json.dumps(follow_up)
    argos.assert_no_http_500()
    argos.assert_no_traceback()


def test_stale_confirmation_and_invalid_write_never_crash_gateway(argos):
    argos.send_chat("onde estou trabalhando agora?")
    repository = SessionRepository(argos.argos_home / "argos.db")
    repository.save_confirmation(
        confirmation_id="stale-search",
        session_id="default",
        run_id="run-search",
        capability="files.search",
        arguments={"pattern": "*.txt"},
    )
    repository.save_confirmation(
        confirmation_id="write-directory",
        session_id="default",
        run_id="run-write",
        capability="file.write",
        arguments={
            "path": str(argos.lab / "backup"),
            "content": "x",
            "mode": "overwrite",
        },
    )
    repository.close()

    search_response = argos._request(
        "POST",
        "/v1/confirmations/stale-search",
        json={"approved": True},
    )
    write_response = argos._request(
        "POST",
        "/v1/confirmations/write-directory",
        json={"approved": True},
    )
    argos.responses.extend([search_response, write_response])

    assert search_response.status_code < 500
    assert "arquivo-a.txt" in search_response.json()["message"]
    assert write_response.status_code < 500
    assert write_response.json()["error_code"] in {
        "permission_denied",
        "invalid_path",
    }
    argos.assert_no_http_500()
    argos.assert_no_traceback()


def test_tools_pending_and_cancel_cli_commands(argos):
    pending = argos.send_chat(
        "quero que me diga a data de criação do arquivo arquivo-a.txt"
    )

    listed = argos.run_cli(
        "tools",
        "pending",
        "--session",
        "default",
    )
    cancelled = argos.run_cli(
        "tools",
        "cancel",
        pending["workflow_id"],
    )

    assert listed.returncode == 0, listed.stderr
    assert pending["workflow_id"] in listed.stdout
    assert cancelled.returncode == 0, cancelled.stderr
    assert argos.list_pending_workflows() == []
