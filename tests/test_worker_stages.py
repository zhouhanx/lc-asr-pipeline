"""Worker stage-resume regression tests."""

from typing import cast
from uuid import uuid4

import pytest
from pydantic import SecretStr

from lc_asr_pipeline import worker
from lc_asr_pipeline.core.config import Settings
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.schemas.refinement import (
    RefinedUtterance,
    TranscriptRefinementResult,
)
from lc_asr_pipeline.schemas.transcription import TranscriptionResult


@pytest.mark.asyncio
async def test_refinement_claim_reuses_checkpoint_without_running_asr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = TranscriptionResult(
        text="语音解析结果",
        language="Chinese",
        segments=[],
        speaker_segments=[],
        provider="saved-speech-provider",
        model="saved-speech-model",
    )
    job = worker.ClaimedJob(
        id=uuid4(),
        tenant_id=uuid4(),
        uploaded_file_id=uuid4(),
        provider_id=uuid4(),
        storage_path="/ignored/checkpoint.wav",
        provider_name="speech",
        provider_type="local",
        base_url="http://127.0.0.1:8765",
        model_name="speech-model",
        api_key_env=None,
        api_key_ciphertext=b"unused-speech-key",
        text_provider_id=uuid4(),
        text_provider_type="deepseek",
        text_base_url="https://api.deepseek.com",
        text_model_name="deepseek-test",
        text_api_key_ciphertext=b"encrypted-text-key",
        language="Chinese",
        diarize=True,
        speaker_mode="double",
        stage="refinement",
        asr_result_checkpoint=checkpoint.model_dump(mode="json"),
        attempt=2,
        refinement_attempt=2,
        max_attempts=3,
    )
    settings = Settings(
        postgres_user="test",
        postgres_password=SecretStr("test"),
        postgres_database="test",
    )

    async def reject_asr(*_: object, **__: object) -> object:
        raise AssertionError("ASR must not run when a checkpoint is available")

    async def refine(
        _: Settings,
        claimed: worker.ClaimedJob,
        *,
        raw_result: TranscriptionResult,
        text_api_key: str,
    ) -> TranscriptRefinementResult:
        assert claimed.id == job.id
        assert raw_result == checkpoint
        assert text_api_key == "decrypted-text-key"
        return TranscriptRefinementResult(
            formatted_text="用户1：语音解析结果",
            utterances=[RefinedUtterance(speaker="用户1", text="语音解析结果")],
            model="deepseek-test",
        )

    monkeypatch.setattr(worker, "_run_asr_stage", reject_asr)
    monkeypatch.setattr(worker, "_run_refinement_stage", refine)
    monkeypatch.setattr(
        worker,
        "decrypt_model_secret",
        lambda *_args, **_kwargs: "decrypted-text-key",
    )

    raw, formatted, refinement = await worker._execute_job_stages(
        cast(Database, object()),
        settings,
        job,
    )

    assert raw == checkpoint
    assert formatted.text == "用户1：语音解析结果"
    assert refinement.model == "deepseek-test"
