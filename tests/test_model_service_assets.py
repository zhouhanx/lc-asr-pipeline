from pathlib import Path

import pytest
from model_service.app import _pyannote_available


def test_pyannote_requires_config_and_binary_weights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_path = tmp_path / "community-1"
    model_path.mkdir()
    monkeypatch.setenv("PYANNOTE_MODEL_ID", str(model_path))
    assert not _pyannote_available()

    (model_path / "config.yaml").write_text("version: 1", encoding="utf-8")
    assert not _pyannote_available()

    weights = model_path / "segmentation"
    weights.mkdir()
    (weights / "pytorch_model.bin").write_bytes(b"weights")
    assert _pyannote_available()
