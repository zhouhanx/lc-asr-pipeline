"""PostgreSQL persistence for resumable uploads."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from psycopg import AsyncConnection

from lc_asr_pipeline.schemas.upload import UploadBatchCreate
from lc_asr_pipeline.services.archive import ExtractedAudio


class UploadRepository:
    async def create_batch(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        user_id: UUID,
        payload: UploadBatchCreate,
        chunk_size: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        total_bytes = sum(item.size_bytes for item in payload.files)
        batch = await (
            await connection.execute(
                """
                INSERT INTO upload_batches
                    (tenant_id, created_by, name, total_bytes, file_count)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, total_bytes, received_bytes, file_count,
                          status, created_at
                """,
                (tenant_id, user_id, payload.name, total_bytes, len(payload.files)),
            )
        ).fetchone()
        assert batch is not None
        files: list[dict[str, Any]] = []
        reused_bytes = 0
        created_files = 0
        for item in payload.files:
            expected_chunks = (item.size_bytes + chunk_size - 1) // chunk_size
            if item.sha256:
                existing = await (
                    await connection.execute(
                        """
                        SELECT id, size_bytes, chunk_size, expected_chunks,
                               received_chunks, status
                        FROM uploaded_files
                        WHERE tenant_id = %s AND sha256 = %s AND size_bytes = %s
                          AND status = 'ready' AND archive_type IS NULL
                          AND storage_path IS NOT NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (tenant_id, item.sha256.lower(), item.size_bytes),
                    )
                ).fetchone()
                if existing is not None:
                    reused_bytes += item.size_bytes
                    files.append(
                        {
                            **dict(existing),
                            "relative_path": item.relative_path,
                            "deduplicated": True,
                        }
                    )
                    continue
            row = await (
                await connection.execute(
                    """
                    INSERT INTO uploaded_files (
                        batch_id, tenant_id, relative_path, original_name, media_type,
                        archive_type, size_bytes, chunk_size, expected_chunks, sha256
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, relative_path, size_bytes, chunk_size,
                              expected_chunks, received_chunks, status
                    """,
                    (
                        batch["id"],
                        tenant_id,
                        item.relative_path,
                        item.relative_path.rsplit("/", 1)[-1],
                        item.media_type,
                        item.archive_type,
                        item.size_bytes,
                        chunk_size,
                        expected_chunks,
                        item.sha256.lower() if item.sha256 else None,
                    ),
                )
            ).fetchone()
            assert row is not None
            created_files += 1
            files.append({**dict(row), "deduplicated": False})
        if reused_bytes:
            batch = await (
                await connection.execute(
                    """
                    UPDATE upload_batches
                    SET received_bytes = %s,
                        status = CASE WHEN %s = 0 THEN 'ready' ELSE status END,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id, name, total_bytes, received_bytes, file_count,
                              status, created_at
                    """,
                    (reused_bytes, created_files, batch["id"]),
                )
            ).fetchone()
            assert batch is not None
        return dict(batch), files

    async def list_history(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            WITH history AS (
                SELECT DISTINCT ON (sha256)
                       id, original_name, relative_path, size_bytes, sha256, created_at
                FROM uploaded_files
                WHERE tenant_id = %s AND status = 'ready' AND sha256 IS NOT NULL
                  AND archive_type IS NULL AND storage_path IS NOT NULL
                ORDER BY sha256, created_at DESC
            )
            SELECT h.id, h.original_name, h.relative_path, h.size_bytes,
                   h.sha256, h.created_at,
                   (SELECT count(*) FROM transcription_jobs j
                    WHERE j.uploaded_file_id = h.id) AS job_count,
                   latest.id AS latest_job_id,
                   latest.status AS latest_job_status
            FROM history h
            LEFT JOIN LATERAL (
                SELECT j.id, j.status
                FROM transcription_jobs j
                WHERE j.uploaded_file_id = h.id
                ORDER BY j.queued_at DESC
                LIMIT 1
            ) latest ON true
            ORDER BY h.created_at DESC
            LIMIT 500
            """,
            (tenant_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_file_for_update(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        file_id: UUID,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                """
                SELECT id, batch_id, relative_path, archive_type, size_bytes, chunk_size,
                       expected_chunks, received_chunks, sha256, status
                FROM uploaded_files
                WHERE id = %s AND tenant_id = %s
                FOR UPDATE
                """,
                (file_id, tenant_id),
            )
        ).fetchone()
        return None if row is None else dict(row)

    async def chunk_rows(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        file_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT chunk_index, offset_bytes, size_bytes, sha256, storage_path
            FROM upload_chunks WHERE file_id = %s ORDER BY chunk_index
            """,
            (file_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def add_extracted_files(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        parent: dict[str, Any],
        tenant_id: UUID,
        extracted: list[ExtractedAudio],
    ) -> list[UUID]:
        file_ids: list[UUID] = []
        for item in extracted:
            relative_path = f"{parent['relative_path']}!/{item.relative_path}"
            row = await (
                await connection.execute(
                    """
                    INSERT INTO uploaded_files (
                        batch_id, tenant_id, parent_file_id, relative_path,
                        original_name, size_bytes, chunk_size, expected_chunks,
                        received_chunks, sha256, storage_path, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 1, %s, %s, 'ready')
                    RETURNING id
                    """,
                    (
                        parent["batch_id"],
                        tenant_id,
                        parent["id"],
                        relative_path,
                        item.relative_path.rsplit("/", 1)[-1],
                        item.size_bytes,
                        max(1024 * 1024, min(item.size_bytes, 64 * 1024 * 1024)),
                        item.sha256,
                        str(item.storage_path),
                    ),
                )
            ).fetchone()
            assert row is not None
            file_ids.append(row["id"])  # type: ignore[arg-type]
        return file_ids

    async def ready_child_ids(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        parent_file_id: UUID,
    ) -> list[UUID]:
        cursor = await connection.execute(
            """
            SELECT id FROM uploaded_files
            WHERE parent_file_id = %s AND status = 'ready'
            ORDER BY relative_path
            """,
            (parent_file_id,),
        )
        rows = await cursor.fetchall()
        return [row["id"] for row in rows]  # type: ignore[misc]

    async def cancel_batch(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        batch_id: UUID,
    ) -> list[UUID] | None:
        batch = await (
            await connection.execute(
                """
                SELECT id FROM upload_batches b
                WHERE b.id = %s AND b.tenant_id = %s
                  AND b.status IN ('uploading', 'ready', 'failed')
                  AND NOT EXISTS (
                      SELECT 1 FROM transcription_jobs j
                      JOIN uploaded_files f ON f.id = j.uploaded_file_id
                      WHERE f.batch_id = b.id
                        AND j.status IN ('queued', 'processing', 'refining', 'completed')
                  )
                FOR UPDATE
                """,
                (batch_id, tenant_id),
            )
        ).fetchone()
        if batch is None:
            return None
        cursor = await connection.execute(
            "SELECT id FROM uploaded_files WHERE batch_id = %s",
            (batch_id,),
        )
        file_ids = [cast(UUID, row["id"]) for row in await cursor.fetchall()]
        await connection.execute(
            """
            UPDATE uploaded_files SET status = 'cancelled', updated_at = now()
            WHERE batch_id = %s AND status <> 'cancelled'
            """,
            (batch_id,),
        )
        await connection.execute(
            """
            UPDATE upload_batches SET status = 'cancelled', updated_at = now()
            WHERE id = %s
            """,
            (batch_id,),
        )
        return file_ids

    async def delete_file_for_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        file_id: UUID,
    ) -> dict[str, Any] | None:
        item = await (
            await connection.execute(
                """
                SELECT id, batch_id, parent_file_id, storage_path
                FROM uploaded_files
                WHERE id = %s AND tenant_id = %s
                FOR UPDATE
                """,
                (file_id, tenant_id),
            )
        ).fetchone()
        if item is None:
            return None
        jobs = await (
            await connection.execute(
                """
                SELECT count(*) AS count,
                       count(*) FILTER (
                           WHERE status IN ('processing', 'refining')
                       ) AS processing
                FROM transcription_jobs
                WHERE tenant_id = %s AND uploaded_file_id = %s
                """,
                (tenant_id, file_id),
            )
        ).fetchone()
        assert jobs is not None
        if int(str(jobs["processing"])) > 0:
            return {**dict(item), "blocked": True}

        deleted_files = 1
        root_file_id: UUID | None = None
        exact_storage_path = str(item["storage_path"]) if item["storage_path"] else None
        parent_file_id = cast(UUID | None, item["parent_file_id"])
        batch_ids = {cast(UUID, item["batch_id"])}
        if parent_file_id is None:
            descendants = await (
                await connection.execute(
                    "SELECT count(*) AS count FROM uploaded_files WHERE parent_file_id = %s",
                    (file_id,),
                )
            ).fetchone()
            assert descendants is not None
            deleted_files += int(str(descendants["count"]))
            root_file_id = file_id

        await connection.execute(
            "DELETE FROM uploaded_files WHERE id = %s AND tenant_id = %s",
            (file_id, tenant_id),
        )

        if parent_file_id is not None:
            parent = await (
                await connection.execute(
                    """
                    SELECT id, batch_id FROM uploaded_files
                    WHERE id = %s AND tenant_id = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM uploaded_files child
                          WHERE child.parent_file_id = uploaded_files.id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM transcription_jobs job
                          WHERE job.uploaded_file_id = uploaded_files.id
                      )
                    FOR UPDATE
                    """,
                    (parent_file_id, tenant_id),
                )
            ).fetchone()
            if parent is not None:
                await connection.execute(
                    "DELETE FROM uploaded_files WHERE id = %s AND tenant_id = %s",
                    (parent_file_id, tenant_id),
                )
                root_file_id = parent_file_id
                exact_storage_path = None
                deleted_files += 1
                batch_ids.add(cast(UUID, parent["batch_id"]))

        for batch_id in batch_ids:
            await connection.execute(
                """
                DELETE FROM upload_batches b
                WHERE b.id = %s AND b.tenant_id = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM uploaded_files f WHERE f.batch_id = b.id
                  )
                """,
                (batch_id, tenant_id),
            )
        return {
            "id": file_id,
            "blocked": False,
            "deleted_jobs": int(str(jobs["count"])),
            "deleted_files": deleted_files,
            "root_file_id": root_file_id,
            "exact_storage_path": exact_storage_path,
        }
