"""Durable PostgreSQL-backed transcription worker."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
from psycopg.types.json import Jsonb

from lc_asr_pipeline.core.config import Settings, get_settings
from lc_asr_pipeline.core.task_identity import log_task_event
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.ocr_worker import (
    claim_ocr_job,
    process_ocr_job,
    recover_stale_ocr_jobs,
)
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
logger = logging.getLogger(__name__)


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
    stage: Literal["asr", "refinement"]
    asr_result_checkpoint: dict[str, object] | None
    attempt: int
    refinement_attempt: int
    max_attempts: int


async def recover_stale_jobs(database: Database) -> int:
    async with database.system_connection() as connection:
        cancelled = await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = 'cancelled', completed_at = now(), last_heartbeat_at = NULL,
                updated_at = now()
            WHERE status IN ('processing', 'refining')
              AND cancel_requested_at IS NOT NULL
              AND last_heartbeat_at < now() - make_interval(secs => %s)
            RETURNING id
            """,
            (STALE_AFTER_SECONDS,),
        )
        requeued = await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = CASE
                    WHEN status = 'refining' AND refinement_attempts < max_attempts
                        THEN 'refining'
                    WHEN status = 'processing' AND attempts < max_attempts
                        THEN 'queued'
                    ELSE 'failed'
                END,
                next_attempt_at = CASE
                    WHEN status = 'refining' AND refinement_attempts < max_attempts
                        THEN now()
                    WHEN status = 'processing' AND attempts < max_attempts
                        THEN now()
                    ELSE NULL
                END,
                completed_at = CASE
                    WHEN status = 'refining' AND refinement_attempts < max_attempts
                        THEN NULL
                    WHEN status = 'processing' AND attempts < max_attempts
                        THEN NULL
                    ELSE now()
                END,
                error_code = 'WorkerLost', error_message = 'Worker stopped during processing',
                progress_percent = CASE WHEN status = 'refining' THEN 75 ELSE 0 END,
                last_heartbeat_at = NULL, updated_at = now()
            WHERE status IN ('processing', 'refining')
              AND cancel_requested_at IS NULL
              AND last_heartbeat_at < now() - make_interval(secs => %s)
            RETURNING id, status
            """,
            (STALE_AFTER_SECONDS,),
        )
        cancelled_rows = await cancelled.fetchall()
        requeued_rows = await requeued.fetchall()
    for row in cancelled_rows:
        log_task_event(
            logger,
            logging.WARNING,
            event="stale_task_cancelled",
            kind="asr",
            task_uuid=row["id"],  # type: ignore[arg-type]
            status="cancelled",
        )
    for row in requeued_rows:
        log_task_event(
            logger,
            logging.WARNING,
            event="stale_task_recovered",
            kind="asr",
            task_uuid=row["id"],  # type: ignore[arg-type]
            status=str(row["status"]),
            safe_message="Worker heartbeat expired",
        )
    return len(cancelled_rows) + len(requeued_rows)


async def claim_job(database: Database) -> ClaimedJob | None:
    async with database.system_connection() as connection:
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
                       CASE WHEN j.status = 'refining'
                            THEN 'refinement' ELSE 'asr' END AS stage,
                       j.asr_result_checkpoint,
                       j.attempts + 1 AS attempt,
                       j.refinement_attempts
                           + CASE WHEN j.status = 'refining' THEN 1 ELSE 0 END
                           AS refinement_attempt,
                       j.max_attempts
                FROM transcription_jobs j
                JOIN uploaded_files f ON f.id = j.uploaded_file_id
                JOIN model_providers p ON p.id = j.provider_id
                WHERE (
                        j.status = 'queued'
                        OR (j.status = 'refining' AND j.last_heartbeat_at IS NULL)
                      )
                  AND f.status = 'ready'
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
            SET status = CASE WHEN status = 'refining' THEN 'refining' ELSE 'processing' END,
                started_at = COALESCE(started_at, now()),
                attempts = attempts + 1,
                refinement_attempts = refinement_attempts
                    + CASE WHEN status = 'refining' THEN 1 ELSE 0 END,
                progress_percent = CASE WHEN status = 'refining' THEN 75 ELSE 1 END,
                last_heartbeat_at = now(), next_attempt_at = NULL, updated_at = now()
            WHERE id = %s
            """,
            (row["id"],),
        )
    job = ClaimedJob(**row)  # type: ignore[arg-type]
    log_task_event(
        logger,
        logging.INFO,
        event="task_claimed",
        kind="asr",
        task_uuid=job.id,
        stage=job.stage,
        attempt=job.refinement_attempt if job.stage == "refinement" else job.attempt,
        status="refining" if job.stage == "refinement" else "processing",
    )
    return job


async def _heartbeat_until_cancel(database: Database, job: ClaimedJob) -> bool:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        async with database.system_connection() as connection:
            row = await (
                await connection.execute(
                    """
                    UPDATE transcription_jobs
                    SET last_heartbeat_at = now(), progress_percent = GREATEST(progress_percent, 5),
                        updated_at = now()
                    WHERE id = %s
                      AND status IN ('processing', 'refining')
                      AND attempts = %s
                    RETURNING cancel_requested_at
                    """,
                    (job.id, job.attempt),
                )
            ).fetchone()
        if row is None or row["cancel_requested_at"] is not None:
            return True


async def _mark_cancelled(database: Database, job: ClaimedJob) -> None:
    async with database.system_connection() as connection:
        changed = await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = 'cancelled', completed_at = now(), last_heartbeat_at = NULL,
                updated_at = now()
            WHERE id = %s
              AND status IN ('processing', 'refining')
              AND attempts = %s
            """,
            (job.id, job.attempt),
        )
    if changed.rowcount == 1:
        log_task_event(
            logger,
            logging.INFO,
            event="task_cancelled",
            kind="asr",
            task_uuid=job.id,
            stage=job.stage,
            attempt=job.attempt,
            status="cancelled",
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
    async with database.system_connection() as connection:
        state = await (
            await connection.execute(
                """
                SELECT status, attempts, cancel_requested_at
                FROM transcription_jobs WHERE id = %s FOR UPDATE
                """,
                (job.id,),
            )
        ).fetchone()
        if state is None or state["status"] != "refining" or state["attempts"] != job.attempt:
            return
        if state["cancel_requested_at"] is not None:
            await connection.execute(
                """
                UPDATE transcription_jobs SET status = 'cancelled', completed_at = now(),
                    last_heartbeat_at = NULL, updated_at = now() WHERE id = %s
                """,
                (job.id,),
            )
            log_task_event(
                logger,
                logging.INFO,
                event="task_cancelled",
                kind="asr",
                task_uuid=job.id,
                stage=job.stage,
                attempt=job.attempt,
                status="cancelled",
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
                    tenant_id, transcript_id, segment_index, start_seconds,
                    end_seconds, speaker, text
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job.tenant_id,
                    transcript["id"],
                    index,
                    segment.start,
                    segment.end,
                    segment.speaker,
                    segment.text,
                ),
            )
        changed = await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = 'completed', completed_at = now(), progress_percent = 100,
                last_heartbeat_at = NULL, error_code = NULL, error_message = NULL,
                updated_at = now()
            WHERE id = %s
            """,
            (job.id,),
        )
    if changed.rowcount == 1:
        log_task_event(
            logger,
            logging.INFO,
            event="task_completed",
            kind="asr",
            task_uuid=job.id,
            stage="refinement",
            attempt=job.refinement_attempt,
            status="completed",
        )


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 409, 425, 429} or exc.response.status_code >= 500
    return isinstance(exc, DeepSeekRefinementError)


async def persist_asr_checkpoint(
    database: Database,
    job: ClaimedJob,
    result: TranscriptionResult,
) -> int:
    async with database.system_connection() as connection:
        row = await (
            await connection.execute(
                """
                UPDATE transcription_jobs
                SET asr_result_checkpoint = %s, asr_completed_at = now(),
                    status = 'refining', progress_percent = 75,
                    refinement_attempts = refinement_attempts + 1,
                    error_code = NULL, error_message = NULL, updated_at = now()
                WHERE id = %s AND status = 'processing' AND attempts = %s
                  AND cancel_requested_at IS NULL
                RETURNING refinement_attempts
                """,
                (Jsonb(result.model_dump(mode="json")), job.id, job.attempt),
            )
        ).fetchone()
    if row is None:
        raise RuntimeError("Job lease was lost before the ASR checkpoint was saved")
    log_task_event(
        logger,
        logging.INFO,
        event="task_stage_completed",
        kind="asr",
        task_uuid=job.id,
        stage="asr",
        attempt=job.attempt,
        status="refining",
    )
    return int(str(row["refinement_attempts"]))


async def _run_asr_stage(
    database: Database,
    settings: Settings,
    job: ClaimedJob,
    api_key: str,
) -> tuple[TranscriptionResult, int]:
    await enforce_provider_network_policy(
        job.base_url,
        allow_private=job.provider_type == "local",
        trusted_hosts={"api.stepfun.com"} if job.provider_type == "stepfun" else (),
    )
    provider: OpenAICompatibleASRProvider | StepFunASRProvider = (
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
    request = TranscriptionRequest(
        audio_path=Path(job.storage_path),
        language=job.language,
        timestamps=True,
        diarize=job.diarize,
    )
    raw_result = await build_transcription_chain(provider).ainvoke(request)
    refinement_attempt = await persist_asr_checkpoint(database, job, raw_result)
    return raw_result, refinement_attempt


async def _run_refinement_stage(
    settings: Settings,
    job: ClaimedJob,
    *,
    raw_result: TranscriptionResult,
    text_api_key: str,
) -> TranscriptRefinementResult:
    await enforce_provider_network_policy(
        job.text_base_url or "",
        allow_private=False,
        trusted_hosts={"api.deepseek.com"} if job.text_provider_type == "deepseek" else (),
    )
    refiner = DeepSeekTranscriptRefiner(
        api_key=text_api_key,
        base_url=job.text_base_url or "",
        model=job.text_model_name or "",
        timeout_seconds=settings.text_model_request_timeout_seconds,
        provider_type=job.text_provider_type or "openai_compatible",
    )
    return await build_transcript_refinement_chain(refiner).ainvoke(
        TranscriptRefinementRequest(
            raw_text=raw_result.text,
            speaker_mode=job.speaker_mode,
            speaker_hints=raw_result.speaker_segments,
        )
    )


async def fail_job(database: Database, job: ClaimedJob, exc: Exception) -> None:
    async with database.system_connection() as connection:
        state = await (
            await connection.execute(
                """
                SELECT status, asr_result_checkpoint, refinement_attempts
                FROM transcription_jobs
                WHERE id = %s AND attempts = %s
                  AND status IN ('processing', 'refining')
                FOR UPDATE
                """,
                (job.id, job.attempt),
            )
        ).fetchone()
        if state is None:
            return
        has_asr_checkpoint = state["asr_result_checkpoint"] is not None
        stage_attempt = (
            int(str(state["refinement_attempts"])) if has_asr_checkpoint else job.attempt
        )
        retry = _is_transient(exc) and stage_attempt < job.max_attempts
        delay = min(300, 2 ** min(stage_attempt, 8))
        message = (
            "Temporary text model failure; refinement retry scheduled"
            if retry and has_asr_checkpoint
            else "Temporary speech model failure; ASR retry scheduled"
            if retry
            else "Text model request failed; ASR result was preserved"
            if has_asr_checkpoint
            else "Speech model request failed"
        )
        changed = await connection.execute(
            """
            UPDATE transcription_jobs
            SET status = %s,
                next_attempt_at = CASE WHEN %s THEN now() + make_interval(secs => %s) ELSE NULL END,
                completed_at = CASE WHEN %s THEN NULL ELSE now() END,
                progress_percent = %s, last_heartbeat_at = NULL,
                error_code = %s, error_message = %s, updated_at = now()
            WHERE id = %s
              AND status IN ('processing', 'refining')
              AND attempts = %s
            """,
            (
                "refining" if retry and has_asr_checkpoint else "queued" if retry else "failed",
                retry,
                delay,
                retry,
                75 if has_asr_checkpoint else 0,
                type(exc).__name__[:80],
                message,
                job.id,
                job.attempt,
            ),
        )
    if changed.rowcount == 1:
        final_status = (
            "refining" if retry and has_asr_checkpoint else "queued" if retry else "failed"
        )
        log_task_event(
            logger,
            logging.WARNING if retry else logging.ERROR,
            event="task_retry_scheduled" if retry else "task_failed",
            kind="asr",
            task_uuid=job.id,
            stage="refinement" if has_asr_checkpoint else "asr",
            attempt=stage_attempt,
            status=final_status,
            retry=retry,
            error=exc,
            safe_message=message,
        )


async def _execute_job_stages(
    database: Database,
    settings: Settings,
    job: ClaimedJob,
) -> tuple[TranscriptionResult, TranscriptionResult, TranscriptRefinementResult]:
    if job.stage == "asr":
        api_key = (
            decrypt_model_secret(
                job.api_key_ciphertext,
                master_secret=settings.model_secret_key,
                tenant_id=job.tenant_id,
            )
            if job.api_key_ciphertext is not None
            else resolve_secret_reference(job.api_key_env)
        )
        if not api_key:
            raise RuntimeError("Provider key is not configured")
        raw_result, _ = await _run_asr_stage(database, settings, job, api_key)
    else:
        if job.asr_result_checkpoint is None:
            raise RuntimeError("ASR checkpoint is missing")
        raw_result = TranscriptionResult.model_validate(job.asr_result_checkpoint)

    text_api_key = (
        decrypt_model_secret(
            job.text_api_key_ciphertext,
            master_secret=settings.model_secret_key,
            tenant_id=job.tenant_id,
        )
        if job.text_api_key_ciphertext is not None
        else None
    )
    if (
        job.text_provider_id is None
        or job.text_base_url is None
        or job.text_model_name is None
        or not text_api_key
    ):
        raise RuntimeError("Text model is not configured")
    refinement = await _run_refinement_stage(
        settings,
        job,
        raw_result=raw_result,
        text_api_key=text_api_key,
    )
    return (
        raw_result,
        raw_result.model_copy(update={"text": refinement.formatted_text}),
        refinement,
    )


async def process_job(database: Database, settings: Settings, job: ClaimedJob) -> None:
    inference = asyncio.create_task(_execute_job_stages(database, settings, job))
    monitor = asyncio.create_task(_heartbeat_until_cancel(database, job))
    done, _ = await asyncio.wait({inference, monitor}, return_when=asyncio.FIRST_COMPLETED)
    if monitor in done:
        inference.cancel()
        await asyncio.gather(inference, return_exceptions=True)
        await _mark_cancelled(database, job)
        return
    monitor.cancel()
    await asyncio.gather(monitor, return_exceptions=True)
    try:
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
    await recover_stale_ocr_jobs(database)
    try:
        while True:
            job = await claim_job(database)
            if job is not None:
                await process_job(database, settings, job)
            ocr_job = None
            if job is None:
                ocr_job = await claim_ocr_job(database)
                if ocr_job is not None:
                    await process_ocr_job(database, settings, ocr_job)
            if once:
                return
            if job is None and ocr_job is None:
                await asyncio.sleep(poll_seconds)
    finally:
        await database.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="Run the LC ASR transcription worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    arguments = parser.parse_args()
    asyncio.run(run_worker(once=arguments.once, poll_seconds=arguments.poll_seconds))


if __name__ == "__main__":
    main()
