"""Task correlation ID and safe logging tests."""

import logging
from uuid import UUID

import pytest

from lc_asr_pipeline.core.task_identity import log_task_event, task_reference
from lc_asr_pipeline.schemas.job import TranscriptionJobResponse
from lc_asr_pipeline.schemas.ocr import OCRJobResponse

TASK_UUID = UUID("5bd78de5-1d72-435d-86ca-afbc3a536b71")


def test_task_references_are_stable_and_type_scoped() -> None:
    assert task_reference("asr", TASK_UUID) == ("ASR-5bd78de5-1d72-435d-86ca-afbc3a536b71")
    assert task_reference("ocr", TASK_UUID) == ("OCR-5bd78de5-1d72-435d-86ca-afbc3a536b71")
    assert TranscriptionJobResponse.model_construct(id=TASK_UUID).model_dump()[
        "task_id"
    ] == task_reference("asr", TASK_UUID)
    assert OCRJobResponse.model_construct(id=TASK_UUID).model_dump()["task_id"] == task_reference(
        "ocr", TASK_UUID
    )


def test_task_failure_log_is_searchable_without_raw_exception_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("test.task-correlation")
    try:
        raise RuntimeError("provider-token-must-not-be-logged")
    except RuntimeError as error:
        with caplog.at_level(logging.ERROR):
            log_task_event(
                logger,
                logging.ERROR,
                event="task_failed",
                kind="ocr",
                task_uuid=TASK_UUID,
                stage="ocr",
                attempt=2,
                status="failed",
                retry=False,
                error=error,
                safe_message="OCR processing failed",
            )

    text = caplog.text
    assert f"task_id={task_reference('ocr', TASK_UUID)}" in text
    assert "event=task_failed" in text
    assert "error_type=RuntimeError" in text
    assert "test_task_identity.py" in text
    assert "provider-token-must-not-be-logged" not in text
