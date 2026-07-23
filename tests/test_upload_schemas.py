import pytest
from pydantic import ValidationError

from lc_asr_pipeline.schemas.upload import UploadBatchCreate


def test_upload_manifest_accepts_folder_paths_and_archives() -> None:
    payload = UploadBatchCreate.model_validate(
        {
            "name": "采访批次",
            "files": [
                {"relative_path": "day-1/interview.wav", "size_bytes": 1024},
                {
                    "relative_path": "archives/source.tar.gz",
                    "size_bytes": 2048,
                    "archive_type": "tar.gz",
                },
            ],
        }
    )
    assert payload.files[0].relative_path == "day-1/interview.wav"


@pytest.mark.parametrize("path", ["../secret.wav", "/etc/passwd", "safe/../secret.wav"])
def test_upload_manifest_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        UploadBatchCreate.model_validate(
            {"name": "unsafe", "files": [{"relative_path": path, "size_bytes": 1}]}
        )

