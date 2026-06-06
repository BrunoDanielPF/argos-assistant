from assistant.config import AppConfig


def test_default_model_prioritizes_local_efficiency():
    assert AppConfig().model == "argos-qwen3:4b"
