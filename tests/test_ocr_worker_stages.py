"""OCR Worker resume-project stage regression tests."""

from typing import cast
from uuid import uuid4

import pytest
from pydantic import SecretStr

from lc_asr_pipeline import ocr_worker
from lc_asr_pipeline.core.config import Settings
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.schemas.ocr import PaddleOCRResult
from lc_asr_pipeline.schemas.resume_project import (
    ExtractedResumeProject,
    ProjectScoreDimension,
    ProjectScoring,
    ResumeProjectExtraction,
)


@pytest.mark.asyncio
async def test_resume_refinement_checkpoint_also_extracts_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = PaddleOCRResult(
        provider_job_id="saved-job",
        markdown_text="# 原始简历",
        page_count=2,
        raw_result={},
    )
    job = ocr_worker.ClaimedOCRJob(
        id=uuid4(),
        tenant_id=uuid4(),
        uploaded_file_id=uuid4(),
        storage_path="/ignored/resume.pdf",
        ocr_provider_id=uuid4(),
        ocr_base_url="https://paddleocr.aistudio-app.com/api/v2/ocr",
        ocr_model_name="PaddleOCR-VL-1.6",
        ocr_api_key_env="PADDLE_API",
        ocr_api_key_ciphertext=None,
        text_provider_id=uuid4(),
        text_provider_type="deepseek",
        text_base_url="https://api.deepseek.com",
        text_model_name="deepseek-test",
        text_api_key_ciphertext=b"encrypted-text-key",
        document_kind="pdf",
        file_attribute="resume",
        stage="refinement",
        ocr_result_checkpoint=checkpoint.model_dump(mode="json"),
        attempt=1,
        refinement_attempt=1,
        max_attempts=3,
    )
    settings = Settings(
        postgres_user="test",
        postgres_password=SecretStr("test"),
        postgres_database="test",
    )

    async def reject_ocr(*_: object, **__: object) -> object:
        raise AssertionError("OCR must not rerun when its checkpoint exists")

    async def refine(
        _: Settings,
        claimed: ocr_worker.ClaimedOCRJob,
        *,
        ocr_result: PaddleOCRResult,
        text_api_key: str,
    ) -> str:
        assert claimed.id == job.id
        assert ocr_result == checkpoint
        assert text_api_key == "decrypted-text-key"
        return "# 校对简历"

    async def extract(
        _: Settings,
        claimed: ocr_worker.ClaimedOCRJob,
        *,
        markdown_text: str,
        text_api_key: str,
    ) -> ResumeProjectExtraction:
        assert claimed.id == job.id
        assert markdown_text == "# 校对简历"
        assert text_api_key == "decrypted-text-key"
        return ResumeProjectExtraction(
            candidate_name="候选人",
            projects=[
                ExtractedResumeProject(
                    project_name="数据平台",
                    scoring=ProjectScoring(
                        architecture_rationality=ProjectScoreDimension(
                            score=8,
                            reason="架构层次明确",
                        ),
                        description_credibility=ProjectScoreDimension(
                            score=7,
                            reason="职责描述具体",
                        ),
                        embellishment_risk=ProjectScoreDimension(
                            score=3,
                            reason="未见明显夸大",
                        ),
                    ),
                )
            ],
            model="deepseek-test",
        )

    monkeypatch.setattr(ocr_worker, "_run_ocr_stage", reject_ocr)
    monkeypatch.setattr(ocr_worker, "_run_refinement_stage", refine)
    monkeypatch.setattr(ocr_worker, "_run_resume_project_extraction", extract)
    monkeypatch.setattr(
        ocr_worker,
        "decrypt_model_secret",
        lambda *_args, **_kwargs: "decrypted-text-key",
    )

    raw, markdown, extraction = await ocr_worker._execute_ocr_stages(
        cast(Database, object()),
        settings,
        job,
    )

    assert raw == checkpoint
    assert markdown == "# 校对简历"
    assert extraction is not None
    assert extraction.projects[0].project_name == "数据平台"
