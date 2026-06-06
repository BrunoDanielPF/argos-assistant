from assistant.config import AppConfig
import pytest
from pydantic import ValidationError


def test_default_model_prioritizes_local_efficiency():
    assert AppConfig().model == "argos-qwen3:4b"


def test_default_ollama_runtime_options_prioritize_responsiveness():
    config = AppConfig()

    assert config.ollama_keep_alive == "10m"
    assert config.ollama_num_predict == 512
    assert config.ollama_num_ctx == 4096
    assert config.ollama_think is False


def test_config_precedence_is_env_then_yaml_then_default(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "schema_version: '1.0'\nmodel: yaml-model\ngateway_port: 17831\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ARGOS_MODEL", "env-model")

    config = AppConfig.load(config_file)

    assert config.model == "env-model"
    assert config.gateway_port == 17831
    assert config.gateway_host == "127.0.0.1"


def test_config_rejects_gateway_bind_outside_loopback(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "schema_version: '1.0'\ngateway_host: 0.0.0.0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        AppConfig.load(config_file)
