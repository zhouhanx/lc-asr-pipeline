"""Durable PostgreSQL-backed transcription worker."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import httpx
from psycopg.types.json import Jsonb

from lc_asr_pipeline.core.config import Settings, get_settings
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.providers.openai_compatible import OpenAICompatibleASRProvider
from lc_asr_pipeline.providers.stepfun import StepFunASRProvider
from lc_asr_pipeline.schemas.refinement import (
    SpeakerMode,
    TranscriptRefinementRequest,
    TranscriptRefinementResult,
)
from lc_asr_pipeline.schemas.transcription import TranscriptionRequest, TranscriptionResult
from lc_asr_pipeline.services.model_secrets import decrypt_model_secret
from lc_asr_pipeline.services.network_policy import enforce_provider_network_policy
from lc_asr_pipeline.services.secrets import resolve_secret_reference
from lc_asr_pipeline.services.transcript_refinement import (
    DeepSeekRefinementError,
    DeepSeekTranscriptRefiner,
    build_transcript_refinement_chain,
)
from lc_asr_pipeline.services.transcription_chain import build_transcription_chain

HEARTBEAT_SECONDS = 15.0
STALE_AFTER_SECONDS = 300


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: UUID
    tenant_id: UUID
    uploaded_file_id: UUID
    provider_id: UUID
    storage_path: str
    provider_name: str
    provider_type: str
    base_url: str
    model_name: str
    api_key_env: str | None
    api_key_ciphertext: bytes | memoryview | None
    text_provider_id: UUID | None
    text_provider_type: str | None
    text_base_url: str | None
    text_model_name: str | None
    text_api_key_ciphertext: bytes | memoryview | None
    language: str | None
    diarize: bool
    speaker_mode: SpeakerMode
    attempt: int
    max_attempts: int


async def recover_stale_jobs(database: Database) -> int:
    async with database.connection() as connection:
        cancelled = await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = 'cancelled', completed_at = now(), last_heartbeat_at = NULL,
                updated_at = now()
            WHERE status = 'processing' AND cancel_requested_at IS NOT NULL
              AND last_heartbeat_at < now() - make_interval(secs => %s)
            """,
            (STALE_AFTER_SECONDS,),
        )
        requeued = await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = CASE WHEN attempts < max_attempts THEN 'queued' ELSE 'failed' END,
                next_attempt_at = CASE WHEN attempts < max_attempts THEN now() ELSE NULL END,
                completed_at = CASE WHEN attempts < max_attempts THEN NULL ELSE now() END,
                error_code = 'WorkerLost', error_message = 'Worker stopped during processing',
                progress_percent = 0, last_heartbeat_at = NULL, updated_at = now()
            WHERE status = 'processing' AND cancel_requested_at IS NULL
              AND last_heartbeat_at < now() - make_interval(secs => %s)
            """,
            (STALE_AFTER_SECONDS,),
        )
    return cancelled.rowcount + requeued.rowcount


async def claim_job(database: Database) -> ClaimedJob | None:
    async with database.connection() as connection:
        row = await (
            await connection.execute(
                """
                SELECT j.id, j.tenant_id, j.uploaded_file_id, j.provider_id,
                       f.storage_path, p.name AS provider_name,
                       j.provider_type_snapshot AS provider_type,
                       j.base_url_snapshot AS base_url,
                       j.model_name_snapshot AS model_name,
                       j.api_key_env_snapshot AS api_key_env,
                       j.api_key_ciphertext_snapshot AS api_key_ciphertext,
                       j.text_provider_id,
                       j.text_provider_type_snapshot AS text_provider_type,
                       j.text_base_url_snapshot AS text_base_url,
                       j.text_model_name_snapshot AS text_model_name,
                       j.text_api_key_ciphertext_snapshot AS text_api_key_ciphertext,
                       j.language, j.diarize, j.speaker_mode,
                       j.attempts + 1 AS attempt,
                       j.max_attempts
                FROM transcription_jobs j
                JOIN uploaded_files f ON f.id = j.uploaded_file_id
                JOIN model_providers p ON p.id = j.provider_id
                WHERE j.status = 'queued' AND f.status = 'ready'
                  AND j.cancel_requested_at IS NULL
                  AND (j.next_attempt_at IS NULL OR j.next_attempt_at <= now())
                ORDER BY j.queued_at
                FOR UPDATE OF j SKIP LOCKED
                LIMIT 1
                """
            )
        ).fetchone()
        if row is None:
            return None
        await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = 'processing', started_at = COALESCE(started_at, now()),
                attempts = attempts + 1, progress_percent = 1,
                last_heartbeat_at = now(), next_attempt_at = NULL, updated_at = now()
            WHERE id = %s
            """,
            (row["id"],),
        )
    return ClaimedJob(**row)  # type: ignore[arg-type]


async def _heartbeat_until_cancel(database: Database, job: ClaimedJob) -> bool:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        async with database.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    UPDATE transcription_jobs
                    SET last_heartbeat_at = now(), progress_percent = GREATEST(progress_percent, 5),
                        updated_at = now()
                    WHERE id = %s AND status = 'processing' AND attempts = %s
                    RETURNING cancel_requested_at
                    """,
                    (job.id, job.attempt),
                )
            ).fetchone()
        if row is None or row["cancel_requested_at"] is not None:
            return True


async def _mark_cancelled(database: Database, job: ClaimedJob) -> None:
    async with database.connection() as connection:
        await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = 'cancelled', completed_at = now(), last_heartbeat_at = NULL,
                updated_at = now()
            WHERE id = %s AND status = 'processing' AND attempts = %s
            """,
            (job.id, job.attempt),
        )


async def persist_result(
    database: Database,
    job: ClaimedJob,
    result: TranscriptionResult,
    *,
    raw_result: TranscriptionResult,
    refinement: TranscriptRefinementResult,
) -> None:
    segments = result.speaker_segments or result.segments
    duration = max((segment.end for segment in segments), default=None)
    async with database.connection() as connection:
        state = await (
            await connection.execute(
                """
                SELECT status, attempts, cancel_requested_at
                FROM transcription_jobs WHERE id = %s FOR UPDATE
                """,
                (job.id,),
            )
        ).fetchone()
        if state is None or state["status"] != "processing" or state["attempts"] != job.attempt:
            return
        if state["cancel_requested_at"] is not None:
            await connection.execute(
                """
                UPDATE transcription_jobs SET status = 'cancelled', completed_at = now(),
                    last_heartbeat_at = NULL, updated_at = now() WHERE id = %s
                """,
                (job.id,),
            )
            return
        transcript = await (
            await connection.execute(
                """
                INSERT INTO transcripts (
                    tenant_id, job_id, uploaded_file_id, provider_id,
                    language, text, duration_seconds, raw_result
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    job.tenant_id,
                    job.id,
                    job.uploaded_file_id,
                    job.provider_id,
                    result.language,
                    result.text,
                    duration,
                    Jsonb(
                        {
                            "asr": raw_result.model_dump(mode="json"),
                            "deepseek": refinement.model_dump(mode="json"),
                        }
                    ),
                ),
            )
        ).fetchone()
        assert transcript is not None
        for index, segment in enumerate(segments):
            await connection.execute(
                """
                INSERT INTO transcript_segments (
                    transcript_id, segment_index, start_seconds,
                    end_seconds, speaker, text
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    transcript["id"], index, segment.start, segment.end,
                    segment.speaker, segment.text,
                ),
            )
        await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = 'completed', completed_at = now(), progress_percent = 100,
                last_heartbeat_at = NULL, error_code = NULL, error_message = NULL,
                updated_at = now()
            WHERE id = %s
            """,
            (job.id,),
        )


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 409, 425, 429} or exc.response.status_code >= 500
    return isinstance(exc, DeepSeekRefinementError)


async def _mark_refinement_started(database: Database, job: ClaimedJob) -> None:
    async with database.connection() as connection:
        await connection.execute(
            """
            UPDATE transcription_jobs
            SET progress_percent = GREATEST(progress_percent, 75), updated_at = now()
            WHERE id = %s AND status = 'processing' AND attempts = %s
            """,
            (job.id, job.attempt),
        )


async def _transcribe_and_refine(
    database: Database,
    settings: Settings,
    job: ClaimedJob,
    provider: OpenAICompatibleASRProvider | StepFunASRProvider,
    text_api_key: str,
) -> tuple[TranscriptionResult, TranscriptionResult, TranscriptRefinementResult]:
    request = TranscriptionRequest(
        audio_path=Path(job.storage_path),
        language=job.language,
        timestamps=True,
        diarize=job.diarize,
    )
    raw_result = await build_transcription_chain(provider).ainvoke(request)
    await _mark_refinement_started(database, job)
    refiner = DeepSeekTranscriptRefiner(
        api_key=text_api_key,
        base_url=job.text_base_url or "",
        model=job.text_model_name or "",
        timeout_seconds=settings.text_model_request_timeout_seconds,
        provider_type=job.text_provider_type or "openai_compatible",
    )
    refinement = await build_transcript_refinement_chain(refiner).ainvoke(
        TranscriptRefinementRequest(
            raw_text=raw_result.text,
            speaker_mode=job.speaker_mode,
            speaker_hints=raw_result.speaker_segments,
        )
    )
    return (
        raw_result,
        raw_result.model_copy(update={"text": refinement.formatted_text}),
        refinement,
    )


async def fail_job(database: Database, job: ClaimedJob, exc: Exception) -> None:
    retry = _is_transient(exc) and job.attempt < job.max_attempts
    delay = min(300, 2 ** min(job.attempt, 8))
    message = (
        "Temporary provider failure; retry scheduled"
        if retry
        else "Model provider request failed"
    )
    async with database.connection() as connection:
        await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = %s,
                next_attempt_at = CASE WHEN %s THEN now() + make_interval(secs => %s) ELSE NULL END,
                completed_at = CASE WHEN %s THEN NULL ELSE now() END,
                progress_percent = 0, last_heartbeat_at = NULL,
                error_code = %s, error_message = %s, updated_at = now()
            WHERE id = %s AND status = 'processing' AND attempts = %s
            """,
            (
                "queued" if retry else "failed",
                retry,
                delay,
                retry,
                type(exc).__name__[:80],
                message,
                job.id,
                job.attempt,
            ),
        )


async def process_job(database: Database, settings: Settings, job: ClaimedJob) -> None:
    try:
        api_key = (
            decrypt_model_secret(
                job.api_key_ciphertext,
                master_secret=settings.model_secret_key,
                tenant_id=job.tenant_id,
            )
            if job.api_key_ciphertext is not None
            else resolve_secret_reference(job.api_key_env)
        )
        text_api_key = (
            decrypt_model_secret(
                job.text_api_key_ciphertext,
                master_secret=settings.model_secret_key,
                tenant_id=job.tenant_id,
            )
            if job.text_api_key_ciphertext is not None
            else None
        )
    except Exception as exc:
        await fail_job(database, job, exc)
        return
    if not api_key:
        await fail_job(database, job, RuntimeError("Provider key is not configured"))
        return
    if (
        job.text_provider_id is None
        or job.text_base_url is None
        or job.text_model_name is None
        or not text_api_key
    ):
        await fail_job(database, job, RuntimeError("Text model is not configured"))
        return
    try:
        await enforce_provider_network_policy(
            job.base_url,
            allow_private=job.provider_type == "local",
            trusted_hosts={"api.stepfun.com"} if job.provider_type == "stepfun" else (),
        )
        await enforce_provider_network_policy(
            job.text_base_url,
            allow_private=False,
            trusted_hosts={"api.deepseek.com"}
            if job.text_provider_type == "deepseek"
            else (),
        )
        provider = (
            StepFunASRProvider(
                name=job.provider_name,
                base_url=job.base_url,
                api_key=api_key,
                model=job.model_name,
                timeout_seconds=settings.asr_request_timeout_seconds,
            )
            if job.provider_type == "stepfun"
            else OpenAICompatibleASRProvider(
                name=job.provider_name,
                base_url=job.base_url,
                api_key=api_key,
                model=job.model_name,
                timeout_seconds=settings.asr_request_timeout_seconds,
            )
        )
        inference = asyncio.create_task(
            _transcribe_and_refine(
                database,
                settings,
                job,
                provider,
                text_api_key,
            )
        )
        monitor = asyncio.create_task(_heartbeat_until_cancel(database, job))
        done, _ = await asyncio.wait({inference, monitor}, return_when=asyncio.FIRST_COMPLETED)
        if monitor in done:
            inference.cancel()
            await asyncio.gather(inference, return_exceptions=True)
            await _mark_cancelled(database, job)
            return
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
        raw_result, refined_result, refinement = inference.result()
        await persist_result(
            database,
            job,
            refined_result,
            raw_result=raw_result,
            refinement=refinement,
        )
    except Exception as exc:
        await fail_job(database, job, exc)


async def run_worker(*, once: bool, poll_seconds: float) -> None:
    settings = get_settings()
    database = Database(settings)
    await database.open()
    await recover_stale_jobs(database)
    try:
        while True:
            job = await claim_job(database)
            if job is not None:
                await process_job(database, settings, job)
            if once:
                return
            if job is None:
                await asyncio.sleep(poll_seconds)
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the LC ASR transcription worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    arguments = parser.parse_args()
    asyncio.run(run_worker(once=arguments.once, poll_seconds=arguments.poll_seconds))


if __name__ == "__main__":
    main()
