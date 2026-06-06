from pathlib import Path


def test_argos_modelfile_customizes_qwen3_4b():
    modelfile = Path(__file__).resolve().parents[1] / "models" / "argos-qwen3-4b.Modelfile"

    content = modelfile.read_text(encoding="utf-8")

    assert "FROM qwen3:4b" in content
    assert "SYSTEM" in content
    assert "Voce e Argos" in content
    assert "Responda em portugues por padrao" in content
    assert "Retorne JSON valido" in content
    assert '"mode":"plan"' in content
    assert "steps" in content
    assert "PARAMETER temperature 0.2" in content
