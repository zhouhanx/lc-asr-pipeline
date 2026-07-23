"""Tenant-scoped transcription job persistence."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from lc_asr_pipeline.schemas.refinement import SpeakerMode


class JobRepository:
    async def create_many(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        user_id: UUID,
        provider_id: UUID,
        text_provider_id: UUID,
        file_ids: list[UUID],
        language: str | None,
        diarize: bool,
        speaker_mode: SpeakerMode,
    ) -> list[dict[str, Any]]:
        provider = await (
            await connection.execute(
                """
                SELECT id, name, provider_type, base_url, model_name,
                       api_key_env, api_key_ciphertext, capabilities
                FROM model_providers
                WHERE id = %s AND tenant_id = %s AND is_enabled
                  AND model_kind = 'speech' AND deleted_at IS NULL
                """,
                (provider_id, tenant_id),
            )
        ).fetchone()
        if provider is None:
            return []
        text_provider = await (
            await connection.execute(
                """
                SELECT id, name, provider_type, base_url, model_name,
                       api_key_ciphertext, capabilities
                FROM model_providers
                WHERE id = %s AND tenant_id = %s AND is_enabled
                  AND model_kind = 'text' AND api_key_ciphertext IS NOT NULL
                  AND deleted_at IS NULL
                """,
                (text_provider_id, tenant_id),
            )
        ).fetchone()
        if text_provider is None:
            return []
        eligible = await (
            await connection.execute(
                """
                SELECT count(*) AS count
                FROM uploaded_files f
                WHERE f.tenant_id = %s AND f.status = 'ready' AND f.id = ANY(%s)
                """,
                (tenant_id, file_ids),
            )
        ).fetchone()
        if eligible is None or int(str(eligible["count"])) != len(file_ids):
            return []
        rows: list[dict[str, Any]] = []
        for file_id in file_ids:
            row = await (
                await connection.execute(
                    """
                    INSERT INTO transcription_jobs (
                        tenant_id, created_by, uploaded_file_id, provider_id, text_provider_id,
                        provider_type_snapshot, base_url_snapshot,
                        model_name_snapshot, api_key_env_snapshot, api_key_ciphertext_snapshot,
                        capabilities_snapshot, text_provider_type_snapshot,
                        text_base_url_snapshot, text_model_name_snapshot,
                        text_api_key_ciphertext_snapshot, text_capabilities_snapshot,
                        language, diarize, speaker_mode
                    )
                    SELECT %s, %s, f.id, %s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s, %s, %s, %s
                    FROM uploaded_files f
                    WHERE f.id = %s AND f.tenant_id = %s AND f.status = 'ready'
                    ON CONFLICT (
                        tenant_id, uploaded_file_id, provider_id, text_provider_id, speaker_mode
                    )
                    DO UPDATE SET updated_at = transcription_jobs.updated_at
                    RETURNING id
                    """,
                    (
                        tenant_id,
                        user_id,
                        provider_id,
                        text_provider_id,
                        provider["provider_type"],
                        provider["base_url"],
                        provider["model_name"],
                        provider["api_key_env"],
                        provider["api_key_ciphertext"],
                        Jsonb(provider["capabilities"]),
                        text_provider["provider_type"],
                        text_provider["base_url"],
                        text_provider["model_name"],
                        text_provider["api_key_ciphertext"],
                        Jsonb(text_provider["capabilities"]),
                        language,
                        diarize,
                        speaker_mode,
                        file_id,
                        tenant_id,
                    ),
                )
            ).fetchone()
            if row is None:
                raise RuntimeError("Concurrent job creation conflict")
            item = await self.get_for_tenant(
                connection,
                tenant_id=tenant_id,
                job_id=row["id"],  # type: ignore[arg-type]
            )
            assert item is not None
            rows.append(item)
        return rows

    async def list_for_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            self._response_query("WHERE j.tenant_id = %s ORDER BY j.queued_at DESC LIMIT 200"),
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
                self._response_query("WHERE j.id = %s AND j.tenant_id = %s"),
                (job_id, tenant_id),
            )
        ).fetchone()
        return None if row is None else dict(row)

    async def update_visibility(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        job_id: UUID,
        visibility: str,
    ) -> dict[str, Any] | None:
        changed = await connection.execute(
            """
            UPDATE transcription_jobs
            SET visibility = %s, updated_at = now()
            WHERE id = %s AND tenant_id = %s
            """,
            (visibility, job_id, tenant_id),
        )
        if changed.rowcount != 1:
            return None
        return await self.get_for_tenant(
            connection,
            tenant_id=tenant_id,
            job_id=job_id,
        )

    async def list_public(
        self,
        connection: AsyncConnection[dict[str, object]],
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            self._public_response_query(
                """
                WHERE j.visibility = 'public' AND tn.status = 'active'
                ORDER BY j.queued_at DESC
                LIMIT 200
                """
            )
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_public(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        job_id: UUID,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                self._public_response_query(
                    """
                    WHERE j.id = %s AND j.visibility = 'public'
                      AND tn.status = 'active'
                    """
                ),
                (job_id,),
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
        await connection.execute(
            """
            UPDATE transcription_jobs
            SET cancel_requested_at = now(),
                status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
                completed_at = CASE WHEN status = 'queued' THEN now() ELSE completed_at END,
                updated_at = now()
            WHERE id = %s AND tenant_id = %s AND status IN ('queued', 'processing')
            """,
            (job_id, tenant_id),
        )
        return await self.get_for_tenant(connection, tenant_id=tenant_id, job_id=job_id)

    async def retry(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> dict[str, Any] | None:
        changed = await (
            await connection.execute(
                """
                UPDATE transcription_jobs
                SET status = 'queued', progress_percent = 0, next_attempt_at = now(),
                    cancel_requested_at = NULL, error_code = NULL, error_message = NULL,
                    started_at = NULL, completed_at = NULL, updated_at = now()
                WHERE id = %s AND tenant_id = %s AND status = 'failed'
                  AND attempts < max_attempts
                RETURNING id
                """,
                (job_id, tenant_id),
            )
        ).fetchone()
        if changed is None:
            return None
        return await self.get_for_tenant(connection, tenant_id=tenant_id, job_id=job_id)

    async def delete_for_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                """
                SELECT id, uploaded_file_id, status
                FROM transcription_jobs
                WHERE id = %s AND tenant_id = %s
                FOR UPDATE
                """,
                (job_id, tenant_id),
            )
        ).fetchone()
        if row is None:
            return None
        if row["status"] == "processing":
            return {**dict(row), "blocked": True, "remaining_jobs": 1}
        await connection.execute(
            "DELETE FROM transcription_jobs WHERE id = %s AND tenant_id = %s",
            (job_id, tenant_id),
        )
        remaining = await (
            await connection.execute(
                """
                SELECT count(*) AS count FROM transcription_jobs
                WHERE tenant_id = %s AND uploaded_file_id = %s
                """,
                (tenant_id, row["uploaded_file_id"]),
            )
        ).fetchone()
        assert remaining is not None
        return {
            **dict(row),
            "blocked": False,
            "remaining_jobs": int(str(remaining["count"])),
        }

    async def segments_for_job(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        job_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT s.segment_index, s.start_seconds, s.end_seconds, s.speaker, s.text
            FROM transcript_segments s
            JOIN transcripts t ON t.id = s.transcript_id
            WHERE t.job_id = %s AND t.tenant_id = %s
            ORDER BY s.segment_index
            """,
            (job_id, tenant_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def segments_for_public_job(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        job_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT s.segment_index, s.start_seconds, s.end_seconds, s.speaker, s.text
            FROM transcript_segments s
            JOIN transcripts t ON t.id = s.transcript_id
            JOIN transcription_jobs j ON j.id = t.job_id
            JOIN tenants tn ON tn.id = j.tenant_id
            WHERE t.job_id = %s AND j.visibility = 'public' AND tn.status = 'active'
            ORDER BY s.segment_index
            """,
            (job_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    @staticmethod
    def _response_query(where_clause: str) -> str:
        return f"""
            SELECT j.id, j.uploaded_file_id, j.provider_id, j.text_provider_id,
                   p.name AS provider_name, tp.name AS text_provider_name,
                   (p.deleted_at IS NOT NULL) AS provider_deleted,
                   (tp.deleted_at IS NOT NULL) AS text_provider_deleted,
                   j.provider_type_snapshot AS provider_type,
                   j.model_name_snapshot AS model_name,
                   j.text_model_name_snapshot AS text_model_name,
                   f.relative_path AS source_path, j.status, j.visibility,
                   j.language, j.diarize,
                   j.speaker_mode,
                   j.progress_percent, j.attempts, j.max_attempts,
                   j.cancel_requested_at, j.error_message, j.queued_at,
                   j.started_at, j.completed_at, t.id AS transcript_id,
                   t.text AS transcript_text
            FROM transcription_jobs j
            JOIN uploaded_files f ON f.id = j.uploaded_file_id
            JOIN model_providers p ON p.id = j.provider_id
            LEFT JOIN model_providers tp ON tp.id = j.text_provider_id
            LEFT JOIN transcripts t ON t.job_id = j.id
            {where_clause}
        """

    @staticmethod
    def _public_response_query(where_clause: str) -> str:
        return f"""
            SELECT j.id, j.uploaded_file_id, j.provider_id, j.text_provider_id,
                   tn.slug AS tenant_slug, tn.name AS tenant_name,
                   p.name AS provider_name, tp.name AS text_provider_name,
                   (p.deleted_at IS NOT NULL) AS provider_deleted,
                   (tp.deleted_at IS NOT NULL) AS text_provider_deleted,
                   j.provider_type_snapshot AS provider_type,
                   j.model_name_snapshot AS model_name,
                   j.text_model_name_snapshot AS text_model_name,
                   f.relative_path AS source_path, j.status, j.visibility,
                   j.language, j.diarize, j.speaker_mode,
                   j.progress_percent, j.attempts, j.max_attempts,
                   j.cancel_requested_at, j.error_message, j.queued_at,
                   j.started_at, j.completed_at, t.id AS transcript_id,
                   t.text AS transcript_text
            FROM transcription_jobs j
            JOIN tenants tn ON tn.id = j.tenant_id
            JOIN uploaded_files f ON f.id = j.uploaded_file_id
            JOIN model_providers p ON p.id = j.provider_id
            LEFT JOIN model_providers tp ON tp.id = j.text_provider_id
            LEFT JOIN transcripts t ON t.job_id = j.id
            {where_clause}
        """
