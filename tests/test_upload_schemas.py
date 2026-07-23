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


def test_upload_manifest_accepts_pdf_and_image_kinds() -> None:
    payload = UploadBatchCreate.model_validate(
        {
            "name": "OCR",
            "files": [
                {
                    "relative_path": "docs/report.pdf",
                    "size_bytes": 10,
                    "file_kind": "pdf",
                },
                {
                    "relative_path": "images/page.png",
                    "size_bytes": 10,
                    "file_kind": "image",
                },
            ],
        }
    )

    assert [item.file_kind for item in payload.files] == ["pdf", "image"]


def test_upload_manifest_rejects_document_kind_extension_mismatch() -> None:
    with pytest.raises(ValidationError):
        UploadBatchCreate.model_validate(
            {
                "name": "OCR",
                "files": [
                    {
                        "relative_path": "docs/report.wav",
                        "size_bytes": 10,
                        "file_kind": "pdf",
                    }
                ],
            }
        )
