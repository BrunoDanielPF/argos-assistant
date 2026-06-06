from assistant.config import AppConfig


def test_default_model_prioritizes_local_efficiency():
    assert AppConfig().model == "argos-qwen3:4b"


def test_default_ollama_runtime_options_prioritize_responsiveness():
    config = AppConfig()

    assert config.ollama_keep_alive == "10m"
    assert config.ollama_num_predict == 512
    assert config.ollama_num_ctx == 4096
    assert config.ollama_think is False
