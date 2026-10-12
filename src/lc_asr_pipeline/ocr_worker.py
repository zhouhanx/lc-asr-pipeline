"""Durable PostgreSQL-backed OCR worker stages."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import httpx
from psycopg.types.json import Jsonb

from lc_asr_pipeline.core.config import Settings
from lc_asr_pipeline.core.task_identity import log_task_event
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.providers.paddleocr import (
    PaddleOCRProvider,
    PaddleOCRProviderError,
)
from lc_asr_pipeline.repositories.resume_projects import ResumeProjectRepository
from lc_asr_pipeline.schemas.ocr import (
    DocumentRefinementRequest,
    PaddleOCRResult,
)
from lc_asr_pipeline.schemas.resume_project import (
    ResumeProjectExtraction,
    ResumeProjectExtractionRequest,
)
from lc_asr_pipeline.services.document_refinement import (
    DocumentTextRefiner,
    build_document_refinement_chain,
)
from lc_asr_pipeline.services.model_secrets import decrypt_model_secret
from lc_asr_pipeline.services.network_policy import enforce_provider_network_policy
from lc_asr_pipeline.services.resume_project_extraction import (
    ResumeProjectExtractionError,
    ResumeProjectExtractor,
    build_resume_project_extraction_chain,
)
from lc_asr_pipeline.services.secrets import resolve_secret_reference

OCRStage = Literal["ocr", "refinement"]
resume_project_repository = ResumeProjectRepository()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedOCRJob:
    id: UUID
    tenant_id: UUID
    uploaded_file_id: UUID
    storage_path: str
    ocr_provider_id: UUID
    ocr_base_url: str
    ocr_model_name: str
    ocr_api_key_env: str | None
    ocr_api_key_ciphertext: bytes | None
    text_provider_id: UUID
    text_provider_type: str
    text_base_url: str
    text_model_name: str
    text_api_key_ciphertext: bytes
    document_kind: Literal["image", "pdf"]
    file_attribute: Literal["resume", "document"]
    stage: OCRStage
    ocr_result_checkpoint: dict[str, Any] | None
    attempt: int
    refinement_attempt: int
    max_attempts: int


async def recover_stale_ocr_jobs(database: Database) -> None:
    async with database.system_connection() as connection:
        recovered = await connection.execute(
            """
            UPDATE ocr_jobs
            SET status = CASE
                    WHEN ocr_result_checkpoint IS NOT NULL THEN 'refining'
                    ELSE 'queued'
                END,
                progress_percent = CASE
                    WHEN ocr_result_checkpoint IS NOT NULL THEN 75
                    ELSE 0
                END,
                next_attempt_at = now(), last_heartbeat_at = NULL,
                error_code = 'stale_worker_recovery',
                error_message = 'OCR worker stopped before completing the stage',
                updated_at = now()
            WHERE status IN ('processing', 'refining')
              AND last_heartbeat_at < now() - interval '2 minutes'
            RETURNING id, status
            """
        )
        rows = await recovered.fetchall()
    for row in rows:
        log_task_event(
            logger,
            logging.WARNING,
            event="stale_task_recovered",
            kind="ocr",
            task_uuid=row["id"],  # type: ignore[arg-type]
            status=str(row["status"]),
            safe_message="Worker heartbeat expired",
        )


async def claim_ocr_job(database: Database) -> ClaimedOCRJob | None:
    async with database.system_connection() as connection:
        row = await (
            await connection.execute(
                """
                SELECT job.id, job.tenant_id, job.uploaded_file_id,
                       file.storage_path, job.ocr_provider_id,
                       job.ocr_base_url_snapshot, job.ocr_model_name_snapshot,
                       job.ocr_api_key_env_snapshot,
                       job.ocr_api_key_ciphertext_snapshot,
                       job.text_provider_id, job.text_provider_type_snapshot,
                       job.text_base_url_snapshot, job.text_model_name_snapshot,
                       job.text_api_key_ciphertext_snapshot, job.document_kind,
                       job.file_attribute,
                       job.ocr_result_checkpoint, job.attempts,
                       job.refinement_attempts, job.max_attempts,
                       CASE
                           WHEN job.status = 'refining' THEN 'refinement'
                           ELSE 'ocr'
                       END AS stage
                FROM ocr_jobs job
                JOIN uploaded_files file ON file.id = job.uploaded_file_id
                WHERE job.status IN ('queued', 'refining')
                  AND job.cancel_requested_at IS NULL
                  AND (job.next_attempt_at IS NULL OR job.next_attempt_at <= now())
                ORDER BY job.queued_at
                FOR UPDATE OF job SKIP LOCKED
                LIMIT 1
                """
            )
        ).fetchone()
        if row is None:
            return None
        stage = str(row["stage"])
        updated = await (
            await connection.execute(
                """
                UPDATE ocr_jobs
                SET status = CASE
                        WHEN status = 'refining' THEN 'refining'
                        ELSE 'processing'
                    END,
                    attempts = attempts
                        + CASE WHEN status = 'queued' THEN 1 ELSE 0 END,
                    refinement_attempts = refinement_attempts
                        + CASE WHEN status = 'refining' THEN 1 ELSE 0 END,
                    progress_percent = CASE
                        WHEN status = 'refining' THEN 75
                        ELSE 1
                    END,
                    started_at = COALESCE(started_at, now()),
                    last_heartbeat_at = now(), next_attempt_at = NULL,
                    error_code = NULL, error_message = NULL, updated_at = now()
                WHERE id = %s
                RETURNING attempts, refinement_attempts
                """,
                (row["id"],),
            )
        ).fetchone()
        assert updated is not None
    job = ClaimedOCRJob(
        id=row["id"],  # type: ignore[arg-type]
        tenant_id=row["tenant_id"],  # type: ignore[arg-type]
        uploaded_file_id=row["uploaded_file_id"],  # type: ignore[arg-type]
        storage_path=str(row["storage_path"]),
        ocr_provider_id=row["ocr_provider_id"],  # type: ignore[arg-type]
        ocr_base_url=str(row["ocr_base_url_snapshot"]),
        ocr_model_name=str(row["ocr_model_name_snapshot"]),
        ocr_api_key_env=(
            str(row["ocr_api_key_env_snapshot"]) if row["ocr_api_key_env_snapshot"] else None
        ),
        ocr_api_key_ciphertext=row["ocr_api_key_ciphertext_snapshot"],  # type: ignore[arg-type]
        text_provider_id=row["text_provider_id"],  # type: ignore[arg-type]
        text_provider_type=str(row["text_provider_type_snapshot"]),
        text_base_url=str(row["text_base_url_snapshot"]),
        text_model_name=str(row["text_model_name_snapshot"]),
        text_api_key_ciphertext=row["text_api_key_ciphertext_snapshot"],  # type: ignore[arg-type]
        document_kind=str(row["document_kind"]),  # type: ignore[arg-type]
        file_attribute=str(row["file_attribute"]),  # type: ignore[arg-type]
        stage=stage,  # type: ignore[arg-type]
        ocr_result_checkpoint=row["ocr_result_checkpoint"],  # type: ignore[arg-type]
        attempt=int(str(updated["attempts"])),
        refinement_attempt=int(str(updated["refinement_attempts"])),
        max_attempts=int(str(row["max_attempts"])),
    )
    log_task_event(
        logger,
        logging.INFO,
        event="task_claimed",
        kind="ocr",
        task_uuid=job.id,
        stage=job.stage,
        attempt=job.refinement_attempt if job.stage == "refinement" else job.attempt,
        status="refining" if job.stage == "refinement" else "processing",
    )
    return job


async def _heartbeat_until_cancel(database: Database, job: ClaimedOCRJob) -> None:
    while True:
        await asyncio.sleep(5)
        async with database.system_connection() as connection:
            row = await (
                await connection.execute(
                    """
                    UPDATE ocr_jobs
                    SET last_heartbeat_at = now(), updated_at = now()
                    WHERE id = %s AND status IN ('processing', 'refining')
                    RETURNING cancel_requested_at
                    """,
                    (job.id,),
                )
            ).fetchone()
        if row is None or row["cancel_requested_at"] is not None:
            return


async def _mark_cancelled(database: Database, job: ClaimedOCRJob) -> None:
    async with database.system_connection() as connection:
        changed = await connection.execute(
            """
            UPDATE ocr_jobs
            SET status = 'cancelled', progress_percent = 0,
                completed_at = now(), last_heartbeat_at = NULL,
                error_code = NULL, error_message = NULL, updated_at = now()
            WHERE id = %s
            """,
            (job.id,),
        )
    if changed.rowcount == 1:
        log_task_event(
            logger,
            logging.INFO,
            event="task_cancelled",
            kind="ocr",
            task_uuid=job.id,
            stage=job.stage,
            attempt=job.attempt,
            status="cancelled",
        )


async def _run_ocr_stage(
    database: Database,
    settings: Settings,
    job: ClaimedOCRJob,
    *,
    api_key: str,
) -> PaddleOCRResult:
    async def progress(extracted: int, total: int) -> None:
        percent = 5 + round((extracted / total) * 65)
        async with database.system_connection() as connection:
            await connection.execute(
                """
                UPDATE ocr_jobs
                SET progress_percent = %s, last_heartbeat_at = now(), updated_at = now()
                WHERE id = %s AND status = 'processing'
                """,
                (max(5, min(70, percent)), job.id),
            )

    provider = PaddleOCRProvider(
        base_url=job.ocr_base_url,
        api_key=api_key,
        model=job.ocr_model_name,
        request_timeout_seconds=settings.ocr_request_timeout_seconds,
        poll_timeout_seconds=settings.ocr_poll_timeout_seconds,
    )
    result = await provider.parse_document(
        Path(job.storage_path),
        progress_callback=progress,
    )
    async with database.system_connection() as connection:
        changed = await connection.execute(
            """
            UPDATE ocr_jobs
            SET status = 'refining', progress_percent = 75,
                provider_job_id = %s, ocr_result_checkpoint = %s,
                ocr_completed_at = now(), last_heartbeat_at = now(),
                updated_at = now()
            WHERE id = %s AND status = 'processing'
            """,
            (result.provider_job_id, Jsonb(result.model_dump(mode="json")), job.id),
        )
    if changed.rowcount == 1:
        log_task_event(
            logger,
            logging.INFO,
            event="task_stage_completed",
            kind="ocr",
            task_uuid=job.id,
            stage="ocr",
            attempt=job.attempt,
            status="refining",
        )
    return result


async def _run_refinement_stage(
    settings: Settings,
    job: ClaimedOCRJob,
    *,
    ocr_result: PaddleOCRResult,
    text_api_key: str,
) -> str:
    await enforce_provider_network_policy(
        job.text_base_url,
        trusted_hosts=({"api.deepseek.com"} if job.text_provider_type == "deepseek" else ()),
    )
    refiner = DocumentTextRefiner(
        api_key=text_api_key,
        base_url=job.text_base_url,
        model=job.text_model_name,
        timeout_seconds=settings.text_model_request_timeout_seconds,
        provider_type=job.text_provider_type,
    )
    result = await build_document_refinement_chain(refiner).ainvoke(
        DocumentRefinementRequest(
            markdown_text=ocr_result.markdown_text,
            document_kind=job.document_kind,
            file_attribute=job.file_attribute,
        )
    )
    return result.markdown_text


async def _run_resume_project_extraction(
    settings: Settings,
    job: ClaimedOCRJob,
    *,
    markdown_text: str,
    text_api_key: str,
) -> ResumeProjectExtraction:
    extractor = ResumeProjectExtractor(
        api_key=text_api_key,
        base_url=job.text_base_url,
        model=job.text_model_name,
        timeout_seconds=settings.text_model_request_timeout_seconds,
        provider_type=job.text_provider_type,
    )
    return await build_resume_project_extraction_chain(extractor).ainvoke(
        ResumeProjectExtractionRequest(markdown_text=markdown_text)
    )


async def _execute_ocr_stages(
    database: Database,
    settings: Settings,
    job: ClaimedOCRJob,
) -> tuple[PaddleOCRResult, str, ResumeProjectExtraction | None]:
    if job.stage == "ocr":
        api_key = (
            decrypt_model_secret(
                job.ocr_api_key_ciphertext,
                master_secret=settings.model_secret_key,
                tenant_id=job.tenant_id,
            )
            if job.ocr_api_key_ciphertext is not None
            else resolve_secret_reference(job.ocr_api_key_env)
        )
        if not api_key:
            raise RuntimeError("OCR provider key is not configured")
        ocr_result = await _run_ocr_stage(
            database,
            settings,
            job,
            api_key=api_key,
        )
    else:
        if job.ocr_result_checkpoint is None:
            raise RuntimeError("OCR checkpoint is missing")
        ocr_result = PaddleOCRResult.model_validate(job.ocr_result_checkpoint)
    text_api_key = decrypt_model_secret(
        job.text_api_key_ciphertext,
        master_secret=settings.model_secret_key,
        tenant_id=job.tenant_id,
    )
    markdown = await _run_refinement_stage(
        settings,
        job,
        ocr_result=ocr_result,
        text_api_key=text_api_key,
    )
    project_extraction = (
        await _run_resume_project_extraction(
            settings,
            job,
            markdown_text=markdown,
            text_api_key=text_api_key,
        )
        if job.file_attribute == "resume"
        else None
    )
    return ocr_result, markdown, project_extraction


async def _persist_result(
    database: Database,
    job: ClaimedOCRJob,
    *,
    ocr_result: PaddleOCRResult,
    markdown_text: str,
    project_extraction: ResumeProjectExtraction | None,
) -> None:
    async with database.system_connection() as connection:
        state = await (
            await connection.execute(
                """
                SELECT status, cancel_requested_at
                FROM ocr_jobs WHERE id = %s FOR UPDATE
                """,
                (job.id,),
            )
        ).fetchone()
        if state is None:
            return
        if state["cancel_requested_at"] is not None:
            await connection.execute(
                """
                UPDATE ocr_jobs
                SET status = 'cancelled', progress_percent = 0,
                    completed_at = now(), last_heartbeat_at = NULL, updated_at = now()
                WHERE id = %s
                """,
                (job.id,),
            )
            log_task_event(
                logger,
                logging.INFO,
                event="task_cancelled",
                kind="ocr",
                task_uuid=job.id,
                stage=job.stage,
                attempt=job.attempt,
                status="cancelled",
            )
            return
        result = await (
            await connection.execute(
                """
            INSERT INTO ocr_results (
                tenant_id, job_id, uploaded_file_id, ocr_provider_id,
                text_provider_id, markdown_text, page_count, raw_result
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (job_id)
            DO UPDATE SET markdown_text = EXCLUDED.markdown_text,
                          page_count = EXCLUDED.page_count,
                          raw_result = EXCLUDED.raw_result
            RETURNING id
            """,
                (
                    job.tenant_id,
                    job.id,
                    job.uploaded_file_id,
                    job.ocr_provider_id,
                    job.text_provider_id,
                    markdown_text,
                    ocr_result.page_count,
                    Jsonb(ocr_result.raw_result),
                ),
            )
        ).fetchone()
        assert result is not None
        if project_extraction is not None:
            await resume_project_repository.replace_extraction(
                connection,
                tenant_id=job.tenant_id,
                ocr_job_id=job.id,
                ocr_result_id=result["id"],  # type: ignore[arg-type]
                uploaded_file_id=job.uploaded_file_id,
                extraction=project_extraction,
            )
        changed = await connection.execute(
            """
            UPDATE ocr_jobs
            SET status = 'completed', progress_percent = 100,
                completed_at = now(), last_heartbeat_at = NULL,
                error_code = NULL, error_message = NULL, updated_at = now()
            WHERE id = %s
            """,
            (job.id,),
        )
    if changed.rowcount == 1:
        log_task_event(
            logger,
            logging.INFO,
            event="task_completed",
            kind="ocr",
            task_uuid=job.id,
            stage="refinement",
            attempt=job.refinement_attempt,
            status="completed",
        )


def _retryable(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        return code in {408, 409, 425, 429} or code >= 500
    return isinstance(error, httpx.RequestError)


def _safe_error_message(error: Exception) -> str:
    if isinstance(error, PaddleOCRProviderError):
        return str(error)
    if isinstance(error, ResumeProjectExtractionError):
        return str(error)
    if isinstance(error, httpx.HTTPStatusError):
        return f"OCR provider returned HTTP {error.response.status_code}."
    if isinstance(error, httpx.RequestError):
        return "OCR provider network request failed; retry is available."
    return "OCR processing failed; retry is available."


async def _fail_job(database: Database, job: ClaimedOCRJob, error: Exception) -> None:
    stage_attempt = job.refinement_attempt if job.stage == "refinement" else job.attempt
    retry = _retryable(error) and stage_attempt < job.max_attempts
    delay_seconds = min(60, 2 ** max(0, stage_attempt - 1))
    async with database.system_connection() as connection:
        changed = await connection.execute(
            """
            UPDATE ocr_jobs
            SET status = CASE
                    WHEN %s AND ocr_result_checkpoint IS NOT NULL THEN 'refining'
                    WHEN %s THEN 'queued'
                    ELSE 'failed'
                END,
                progress_percent = CASE
                    WHEN %s AND ocr_result_checkpoint IS NOT NULL THEN 75
                    WHEN %s THEN 0
                    ELSE progress_percent
                END,
                next_attempt_at = CASE
                    WHEN %s THEN now() + (%s * interval '1 second')
                    ELSE NULL
                END,
                last_heartbeat_at = NULL,
                completed_at = CASE WHEN %s THEN NULL ELSE now() END,
                error_code = %s,
                error_message = %s,
                updated_at = now()
            WHERE id = %s
            RETURNING status
            """,
            (
                retry,
                retry,
                retry,
                retry,
                retry,
                delay_seconds,
                retry,
                error.__class__.__name__[:80],
                _safe_error_message(error)[:500],
                job.id,
            ),
        )
        changed_row = await changed.fetchone()
    if changed_row is not None:
        log_task_event(
            logger,
            logging.WARNING if retry else logging.ERROR,
            event="task_retry_scheduled" if retry else "task_failed",
            kind="ocr",
            task_uuid=job.id,
            stage=job.stage,
            attempt=stage_attempt,
            status=str(changed_row["status"]),
            retry=retry,
            error=error,
            safe_message=_safe_error_message(error),
        )


async def process_ocr_job(database: Database, settings: Settings, job: ClaimedOCRJob) -> None:
    inference = asyncio.create_task(_execute_ocr_stages(database, settings, job))
    monitor = asyncio.create_task(_heartbeat_until_cancel(database, job))
    done, _ = await asyncio.wait(
        {inference, monitor},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if monitor in done:
        inference.cancel()
        await asyncio.gather(inference, return_exceptions=True)
        await _mark_cancelled(database, job)
        return
    monitor.cancel()
    await asyncio.gather(monitor, return_exceptions=True)
    try:
        ocr_result, markdown, project_extraction = inference.result()
        await _persist_result(
            database,
            job,
            ocr_result=ocr_result,
            markdown_text=markdown,
            project_extraction=project_extraction,
        )
    except Exception as error:
        await _fail_job(database, job, error)
