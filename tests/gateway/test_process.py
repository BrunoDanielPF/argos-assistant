from assistant.config import AppConfig
import os

from assistant.gateway.process import GatewayProcessManager, _process_exists


def test_process_exists_detects_current_process():
    assert _process_exists(os.getpid()) is True


def test_stale_pid_file_is_removed(tmp_path):
    config = AppConfig(
        gateway_pid_file=tmp_path / "gateway.pid",
        gateway_log_file=tmp_path / "gateway.log",
    )
    manager = GatewayProcessManager(
        config,
        process_exists=lambda pid: False,
    )
    manager.pid_file.parent.mkdir(parents=True, exist_ok=True)
    manager.pid_file.write_text("999999", encoding="ascii")

    assert manager.status().running is False
    assert not manager.pid_file.exists()


def test_start_records_spawned_process_id(tmp_path):
    class FakeProcess:
        pid = 321

    calls = []
    config = AppConfig(
        gateway_pid_file=tmp_path / "gateway.pid",
        gateway_log_file=tmp_path / "gateway.log",
    )
    manager = GatewayProcessManager(
        config,
        process_exists=lambda pid: False,
        process_spawner=lambda *args, **kwargs: calls.append((args, kwargs))
        or FakeProcess(),
    )

    status = manager.start()

    assert status.running is True
    assert status.pid == 321
    assert manager.pid_file.read_text(encoding="ascii") == "321"
    assert calls
    assert calls[0][1]["env"]["PYTHONUNBUFFERED"] == "1"
