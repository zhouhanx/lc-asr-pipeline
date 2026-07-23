"""Tenant-scoped OCR job persistence."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from lc_asr_pipeline.core.task_identity import log_task_event

logger = logging.getLogger(__name__)


class OCRJobRepository:
    @staticmethod
    def _response_query(where: str) -> str:
        return f"""
            SELECT job.id, job.uploaded_file_id, job.ocr_provider_id,
                   job.text_provider_id,
                   ocr_provider.name AS ocr_provider_name,
                   text_provider.name AS text_provider_name,
                   (ocr_provider.deleted_at IS NOT NULL) AS ocr_provider_deleted,
                   (text_provider.deleted_at IS NOT NULL) AS text_provider_deleted,
                   job.ocr_model_name_snapshot AS ocr_model_name,
                   job.text_model_name_snapshot AS text_model_name,
                   file.relative_path AS source_path,
                   job.document_kind, job.file_attribute,
                   job.status, job.progress_percent,
                   job.attempts, job.refinement_attempts, job.max_attempts,
                   (job.ocr_result_checkpoint IS NOT NULL) AS has_ocr_checkpoint,
                   job.ocr_completed_at, job.queued_at, job.started_at,
                   job.completed_at, result.id AS result_id,
                   result.markdown_text, COALESCE(result.page_count, 0) AS page_count,
                   COALESCE(result.raw_result, '{{}}'::jsonb) AS raw_result,
                   job.error_message
            FROM ocr_jobs job
            JOIN uploaded_files file ON file.id = job.uploaded_file_id
            JOIN model_providers ocr_provider ON ocr_provider.id = job.ocr_provider_id
            JOIN model_providers text_provider ON text_provider.id = job.text_provider_id
            LEFT JOIN ocr_results result ON result.job_id = job.id
            {where}
        """

    async def create_jobs(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        user_id: UUID,
        ocr_provider_id: UUID,
        text_provider_id: UUID,
        file_ids: list[UUID],
        document_kind: str,
        file_attribute: str,
    ) -> list[dict[str, Any]]:
        ocr_provider = await (
            await connection.execute(
                """
                SELECT provider_type, base_url, model_name, api_key_env,
                       api_key_ciphertext, capabilities
                FROM model_providers
                WHERE id = %s AND tenant_id = %s AND is_enabled
                  AND model_kind = 'ocr' AND provider_type = 'paddleocr'
                  AND deleted_at IS NULL
                """,
                (ocr_provider_id, tenant_id),
            )
        ).fetchone()
        text_provider = await (
            await connection.execute(
                """
                SELECT provider_type, base_url, model_name, api_key_ciphertext,
                       capabilities
                FROM model_providers
                WHERE id = %s AND tenant_id = %s AND is_enabled
                  AND model_kind = 'text' AND api_key_ciphertext IS NOT NULL
                  AND deleted_at IS NULL
                """,
                (text_provider_id, tenant_id),
            )
        ).fetchone()
        if ocr_provider is None or text_provider is None:
            return []
        eligible = await (
            await connection.execute(
                """
                SELECT count(*) AS count
                FROM uploaded_files
                WHERE tenant_id = %s AND status = 'ready'
                  AND file_kind = %s AND id = ANY(%s)
                """,
                (tenant_id, document_kind, file_ids),
            )
        ).fetchone()
        if eligible is None or int(str(eligible["count"])) != len(file_ids):
            return []

        rows: list[dict[str, Any]] = []
        for file_id in file_ids:
            inserted = await (
                await connection.execute(
                    """
                    INSERT INTO ocr_jobs (
                        tenant_id, created_by, uploaded_file_id,
                        ocr_provider_id, text_provider_id,
                        ocr_provider_type_snapshot, ocr_base_url_snapshot,
                        ocr_model_name_snapshot, ocr_api_key_env_snapshot,
                        ocr_api_key_ciphertext_snapshot, ocr_capabilities_snapshot,
                        text_provider_type_snapshot, text_base_url_snapshot,
                        text_model_name_snapshot, text_api_key_ciphertext_snapshot,
                        text_capabilities_snapshot, document_kind, file_attribute
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (
                        tenant_id, uploaded_file_id, ocr_provider_id, text_provider_id,
                        file_attribute
                    )
                    DO UPDATE SET updated_at = ocr_jobs.updated_at
                    RETURNING id
                    """,
                    (
                        tenant_id,
                        user_id,
                        file_id,
                        ocr_provider_id,
                        text_provider_id,
                        ocr_provider["provider_type"],
                        ocr_provider["base_url"],
                        ocr_provider["model_name"],
                        ocr_provider["api_key_env"],
                        ocr_provider["api_key_ciphertext"],
                        Jsonb(ocr_provider["capabilities"]),
                        text_provider["provider_type"],
                        text_provider["base_url"],
                        text_provider["model_name"],
                        text_provider["api_key_ciphertext"],
                        Jsonb(text_provider["capabilities"]),
                        document_kind,
                        file_attribute,
                    ),
                )
            ).fetchone()
            assert inserted is not None
            item = await self.get_for_tenant(
                connection,
                tenant_id=tenant_id,
                job_id=inserted["id"],  # type: ignore[arg-type]
            )
            assert item is not None
            rows.append(item)
            log_task_event(
                logger,
                logging.INFO,
                event="task_created",
                kind="ocr",
                task_uuid=inserted["id"],  # type: ignore[arg-type]
                status=str(item["status"]),
            )
        return rows

    async def list_for_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            self._response_query("WHERE job.tenant_id = %s ORDER BY job.queued_at DESC LIMIT 200"),
            (tenant_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_for_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                self._response_query("WHERE job.id = %s AND job.tenant_id = %s"),
                (job_id, tenant_id),
            )
        ).fetchone()
        return None if row is None else dict(row)

    async def request_cancel(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                """
                UPDATE ocr_jobs
                SET cancel_requested_at = now(),
                    status = CASE
                        WHEN status IN ('queued', 'refining') THEN 'cancelled'
                        ELSE status
                    END,
                    completed_at = CASE
                        WHEN status IN ('queued', 'refining') THEN now()
                        ELSE completed_at
                    END,
                    updated_at = now()
                WHERE id = %s AND tenant_id = %s
                  AND status IN ('queued', 'processing', 'refining')
                RETURNING id
                """,
                (job_id, tenant_id),
            )
        ).fetchone()
        if row is None:
            return None
        return await self.get_for_tenant(connection, tenant_id=tenant_id, job_id=job_id)

    async def retry(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
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
                    attempts = CASE
                        WHEN ocr_result_checkpoint IS NULL THEN 0
                        ELSE attempts
                    END,
                    refinement_attempts = CASE
                        WHEN ocr_result_checkpoint IS NOT NULL THEN 0
                        ELSE refinement_attempts
                    END,
                    next_attempt_at = NULL, cancel_requested_at = NULL,
                    error_code = NULL, error_message = NULL,
                    completed_at = NULL, updated_at = now()
                WHERE id = %s AND tenant_id = %s AND status = 'failed'
                RETURNING id
                """,
                (job_id, tenant_id),
            )
        ).fetchone()
        if row is None:
            return None
        return await self.get_for_tenant(connection, tenant_id=tenant_id, job_id=job_id)

    async def delete(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> str:
        row = await (
            await connection.execute(
                """
                SELECT status FROM ocr_jobs
                WHERE id = %s AND tenant_id = %s FOR UPDATE
                """,
                (job_id, tenant_id),
            )
        ).fetchone()
        if row is None:
            return "not_found"
        if row["status"] in {"processing", "refining"}:
            return "active"
        await connection.execute(
            "DELETE FROM ocr_jobs WHERE id = %s AND tenant_id = %s",
            (job_id, tenant_id),
        )
        return "deleted"
