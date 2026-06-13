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
    ("message", "error_code", "blocked_reasons"),
    [
        (
            "crie uma capacidade para rodar qualquer comando shell que eu pedir",
            "unsupported_capability",
            ["shell_capability_disabled"],
        ),
        (
            "crie uma capacidade para baixar dados da internet e salvar em arquivo",
            "capability_gap",
            ["network_not_allowed", "filesystem_write_not_allowed"],
        ),
    ],
)
def test_effectful_flexible_capabilities_are_terminally_blocked(
    argos,
    message,
    error_code,
    blocked_reasons,
):
    response = argos.send_chat(message)

    assert response["ok"] is False
    assert response["status"] == "completed"
    assert response["error_code"] == error_code
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


@pytest.mark.parametrize(
    "message",
    [
        "rode o comando dir",
        "execute o comando echo teste",
        "no terminal rode git status",
    ],
)
def test_shell_intents_never_become_file_actions(argos, message):
    response = argos.send_chat(message)

    assert response["ok"] is False
    assert response["error_code"] == "unsupported_capability"
    assert response["confirmation"] is None
    snapshot = argos.read_session()
    assert snapshot["audit"][-1]["capability"] == "shell.run"
    assert "file." not in snapshot["audit"][-1]["capability"]
    argos.assert_no_http_500()
    argos.assert_no_traceback()


def test_environment_path_guard_and_file_move_intent(argos):
    move = argos.send_chat(
        "mova arquivos txt para uma pasta backup",
        session="move-files",
    )
    path = argos.send_chat(
        "adicione C:\\tools ao PATH do Windows",
        session="explicit-path",
    )

    assert move["status"] == "waiting_confirmation"
    assert move["confirmation"]["capability"] == "file.move_many"
    assert move["confirmation"]["arguments_summary"]["source_root"] == str(
        argos.lab
    )
    assert move["confirmation"]["arguments_summary"]["destination"] == str(
        argos.lab / "backup"
    )
    assert "modify_path" not in json.dumps(move)
    assert path["error_code"] in {
        "unsupported_capability",
        "capability_gap",
    }
    path_snapshot = argos.read_session("explicit-path")
    assert path_snapshot["audit"][-1]["capability"] == "modify_path"
    argos.assert_no_http_500()
    argos.assert_no_traceback()


def test_file_intents_and_relative_paths_use_runtime_cwd(argos):
    repository = SessionRepository(argos.argos_home / "argos.db")
    repository.save(
        "operational-path",
        {
            "history": [],
            "audit": [],
            "suggestions": [],
            "context": {
                "session_id": "operational-path",
                "current_cwd": None,
                "default_search_root": None,
                "user_home": "C:\\Users\\nome-antigo",
                "last_search_results": [],
                "pending_clarification": None,
                "active_task": None,
            },
        },
    )
    repository.close()

    create_file = argos.send_chat(
        "crie um arquivo chamado novo.txt",
        session="operational-path",
    )
    create_directory = argos.send_chat(
        "crie uma pasta chamada docs",
        session="create-directory",
    )
    read_file = argos.send_chat(
        "leia o arquivo arquivo-a.txt",
        session="read-file",
    )
    open_file = argos.send_chat(
        "abra o arquivo arquivo-inexistente.txt",
        session="open-file",
    )

    assert create_file["confirmation"]["capability"] == "file.create"
    assert create_file["confirmation"]["arguments_summary"]["path"] == str(
        argos.lab / "novo.txt"
    )
    assert "nome-antigo" not in json.dumps(create_file)
    assert create_directory["confirmation"]["capability"] == (
        "file.create_directory"
    )
    assert create_directory["confirmation"]["arguments_summary"]["path"] == str(
        argos.lab / "docs"
    )
    assert read_file["ok"] is True
    assert read_file["message"] == "A"
    assert argos.read_session("read-file")["audit"][-1]["capability"] == (
        "file.read"
    )
    assert open_file["ok"] is False
    assert open_file["error_code"] == "not_found"
    assert argos.read_session("open-file")["audit"][-1]["capability"] == (
        "file.open"
    )
    argos.assert_no_http_500()
    argos.assert_no_traceback()


@pytest.mark.parametrize(
    "marker",
    ["nesta pasta", "aqui", "na pasta atual"],
)
def test_search_markers_use_current_cwd(argos, marker):
    response = argos.send_chat(
        f"liste os arquivos txt {marker}",
        session=f"search-{marker}",
    )

    assert response["ok"] is True
    assert "arquivo-a.txt" in response["message"]
    assert "arquivo-b.txt" in response["message"]
    assert str(argos.lab) in response["message"]
    argos.assert_no_http_500()
    argos.assert_no_traceback()


def test_destructive_dry_run_is_human_readable_and_side_effect_free(argos):
    simulation = argos.send_chat(
        "simule apagar arquivos .tmp nesta pasta",
        session="delete-simulation",
    )
    real_delete = argos.send_chat(
        "apague o arquivo lixo.tmp",
        session="delete-real",
    )

    assert simulation["ok"] is True
    assert "simulacao" in simulation["message"].lower()
    assert "recursos afetados" in simulation["message"].lower()
    assert "lixo.tmp" in simulation["message"]
    assert "nenhum arquivo foi alterado" in simulation["message"].lower()
    assert (argos.lab / "lixo.tmp").exists()
    assert real_delete["status"] == "waiting_confirmation"
    assert real_delete["confirmation"]["capability"] == "file.delete_one"
    assert real_delete["confirmation"]["dry_run"]["requires_confirmation"] is True
    assert (argos.lab / "lixo.tmp").exists()
    argos.assert_no_http_500()
    argos.assert_no_traceback()


def test_search_no_results_is_domain_result_without_dangerous_recovery(argos):
    response = argos.send_chat(
        "liste os arquivos csv nesta pasta",
        session="no-results",
    )

    assert response["ok"] is True
    assert response["error_code"] == "no_results"
    assert response["confirmation"] is None
    recovery_log = argos.argos_home / "audit" / "recovery.jsonl"
    if recovery_log.exists():
        assert '"failure_type": "no_results"' not in recovery_log.read_text(
            encoding="utf-8"
        )
    assert argos.list_pending_workflows(session="no-results") == []
    argos.assert_no_http_500()
    argos.assert_no_traceback()
