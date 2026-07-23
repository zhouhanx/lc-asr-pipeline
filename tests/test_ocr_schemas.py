"""OCR and model-kind schema validation."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from lc_asr_pipeline.schemas.model_provider import ModelProviderCreate
from lc_asr_pipeline.schemas.ocr import OCRJobCreate


def test_paddleocr_is_valid_only_for_ocr_kind() -> None:
    provider = ModelProviderCreate.model_validate(
        {
            "name": "PaddleOCR",
            "model_kind": "ocr",
            "provider_type": "paddleocr",
            "base_url": "https://paddleocr.aistudio-app.com/api/v2/ocr",
            "model_name": "PaddleOCR-VL-1.6",
            "api_key": "test-token",
        }
    )
    assert provider.model_kind == "ocr"

    with pytest.raises(ValidationError):
        ModelProviderCreate.model_validate(
            {
                "name": "Invalid",
                "model_kind": "speech",
                "provider_type": "paddleocr",
                "base_url": "https://paddleocr.aistudio-app.com/api/v2/ocr",
                "model_name": "PaddleOCR-VL-1.6",
                "api_key": "test-token",
            }
        )


def test_ocr_job_defaults_to_document_attribute() -> None:
    payload = OCRJobCreate(
        ocr_provider_id=uuid4(),
        text_provider_id=uuid4(),
        uploaded_file_ids=[uuid4()],
        document_kind="pdf",
    )

    assert payload.file_attribute == "document"


def test_ocr_job_accepts_resume_attribute() -> None:
    payload = OCRJobCreate(
        ocr_provider_id=uuid4(),
        text_provider_id=uuid4(),
        uploaded_file_ids=[uuid4()],
        document_kind="pdf",
        file_attribute="resume",
    )

    assert payload.file_attribute == "resume"


def test_ocr_job_rejects_unknown_file_attribute() -> None:
    with pytest.raises(ValidationError):
        OCRJobCreate.model_validate(
            {
                "ocr_provider_id": str(uuid4()),
                "text_provider_id": str(uuid4()),
                "uploaded_file_ids": [str(uuid4())],
                "document_kind": "pdf",
                "file_attribute": "contract",
            }
        )
