import io
import zipfile
from pathlib import Path

import pytest

from lc_asr_pipeline.services.archive import extract_audio_archive


def create_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def test_extract_audio_archive_preserves_safe_mapping(tmp_path: Path) -> None:
    archive = tmp_path / "audio.zip"
    create_zip(archive, {"访谈/day-1.wav": b"RIFF-audio", "notes.txt": b"ignore"})
    extracted = extract_audio_archive(
        archive,
        tmp_path / "output",
        archive_type="zip",
        max_bytes=1024,
    )
    assert extracted[0].relative_path == "访谈/day-1.wav"
    assert extracted[0].storage_path.read_bytes() == b"RIFF-audio"


def test_extract_audio_archive_rejects_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    create_zip(archive, {"../escape.wav": b"RIFF"})
    with pytest.raises(ValueError, match="unsafe path"):
        extract_audio_archive(
            archive,
            tmp_path / "output",
            archive_type="zip",
            max_bytes=1024,
        )
    assert not (tmp_path / "escape.wav").exists()


def test_extract_audio_archive_enforces_expanded_size(tmp_path: Path) -> None:
    archive = tmp_path / "large.zip"
    buffer = io.BytesIO(b"RIFF" + b"0" * 100)
    create_zip(archive, {"large.wav": buffer.getvalue()})
    with pytest.raises(ValueError, match="configured limit"):
        extract_audio_archive(
            archive,
            tmp_path / "output",
            archive_type="zip",
            max_bytes=10,
        )

