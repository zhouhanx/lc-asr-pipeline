"""Scheduled retention, queued storage deletion, and guarded orphan scanning."""

from __future__ import annotations

import argparse
import asyncio
import time
from typing import cast
from uuid import UUID

from lc_asr_pipeline.core.config import Settings, get_settings
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.services.storage import (
    StorageDeletionSummary,
    process_pending_storage_deletions,
)


async def cleanup_expired(
    *,
    apply: bool,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """Delete expired staging rows and durably queue their physical roots."""
    active_settings = settings or get_settings()
    database = Database(active_settings)
    await database.open()
    try:
        async with database.system_connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT b.id AS batch_id, b.tenant_id,
                           count(f.id) AS file_count,
                           array_remove(
                               array_agg(f.id) FILTER (WHERE f.parent_file_id IS NULL),
                               NULL
                           ) AS root_file_ids
                    FROM upload_batches b
                    LEFT JOIN uploaded_files f ON f.batch_id = b.id
                    WHERE b.expires_at <= now()
                      AND b.status IN ('uploading', 'cancelled', 'failed')
                    GROUP BY b.id, b.tenant_id
                    ORDER BY b.id
                    LIMIT %s
                    """,
                    (active_settings.retention_batch_limit,),
                )
            ).fetchall()
        if not apply:
            return len(rows), sum(cast(int, row["file_count"]) for row in rows)

        deleted_files = 0
        deleted_batches = 0
        async with database.system_connection() as connection:
            locked = await (
                await connection.execute(
                    """
                    SELECT pg_try_advisory_xact_lock(
                        hashtext('lc_asr_pipeline_retention_expired')
                    ) AS locked
                    """
                )
            ).fetchone()
            if locked is None or locked["locked"] is not True:
                return 0, 0
            for row in rows:
                tenant_id = cast(UUID, row["tenant_id"])
                current = await (
                    await connection.execute(
                        """
                        SELECT id
                        FROM upload_batches
                        WHERE id = %s AND tenant_id = %s AND expires_at <= now()
                          AND status IN ('uploading', 'cancelled', 'failed')
                        FOR UPDATE
                        """,
                        (row["batch_id"], tenant_id),
                    )
                ).fetchone()
                if current is None:
                    continue
                files = await (
                    await connection.execute(
                        """
                        SELECT count(*) AS file_count,
                               array_remove(
                                   array_agg(id) FILTER (WHERE parent_file_id IS NULL),
                                   NULL
                               ) AS root_file_ids
                        FROM uploaded_files
                        WHERE batch_id = %s AND tenant_id = %s
                        """,
                        (row["batch_id"], tenant_id),
                    )
                ).fetchone()
                assert files is not None
                root_file_ids = cast(list[UUID] | None, files["root_file_ids"]) or []
                for root_file_id in root_file_ids:
                    await connection.execute(
                        """
                        INSERT INTO storage_deletion_queue (
                            tenant_id, root_file_id, reason
                        )
                        VALUES (%s, %s, 'expired_upload')
                        """,
                        (tenant_id, root_file_id),
                    )
                deleted = await connection.execute(
                    """
                    DELETE FROM upload_batches
                    WHERE id = %s AND tenant_id = %s AND expires_at <= now()
                      AND status IN ('uploading', 'cancelled', 'failed')
                    """,
                    (row["batch_id"], tenant_id),
                )
                if deleted.rowcount == 1:
                    deleted_batches += 1
                    deleted_files += cast(int, files["file_count"])
        await process_pending_storage_deletions(
            database,
            data_path=active_settings.data_path,
            limit=active_settings.retention_batch_limit,
        )
        return deleted_batches, deleted_files
    finally:
        await database.close()


def _orphan_candidates(settings: Settings) -> list[tuple[UUID, UUID]]:
    uploads_root = settings.data_path.resolve() / "uploads"
    if not uploads_root.is_dir():
        return []
    cutoff = time.time() - settings.retention_orphan_grace_seconds
    candidates: list[tuple[UUID, UUID]] = []
    for tenant_path in uploads_root.iterdir():
        if tenant_path.is_symlink() or not tenant_path.is_dir():
            continue
        try:
            tenant_id = UUID(tenant_path.name)
        except ValueError:
            continue
        for file_path in tenant_path.iterdir():
            if file_path.is_symlink() or not file_path.is_dir():
                continue
            try:
                file_id = UUID(file_path.name)
            except ValueError:
                continue
            try:
                if file_path.stat().st_mtime > cutoff:
                    continue
            except OSError:
                continue
            candidates.append((tenant_id, file_id))
            if len(candidates) >= settings.retention_batch_limit:
                return candidates
    return candidates


async def scan_orphan_uploads(
    *,
    apply: bool,
    settings: Settings | None = None,
) -> tuple[int, int]:
    """Find old UUID-shaped upload roots that have no root database record."""
    active_settings = settings or get_settings()
    disk_candidates = _orphan_candidates(active_settings)
    if not disk_candidates:
        return 0, 0
    database = Database(active_settings)
    await database.open()
    try:
        async with database.system_connection() as connection:
            referenced_rows = await (
                await connection.execute(
                    """
                    SELECT tenant_id, id
                    FROM uploaded_files
                    WHERE parent_file_id IS NULL
                    """
                )
            ).fetchall()
        referenced = {
            (cast(UUID, row["tenant_id"]), cast(UUID, row["id"])) for row in referenced_rows
        }
        orphans = [candidate for candidate in disk_candidates if candidate not in referenced]
        if not apply or not orphans:
            return len(orphans), 0

        enqueued = 0
        async with database.system_connection() as connection:
            locked = await (
                await connection.execute(
                    """
                    SELECT pg_try_advisory_xact_lock(
                        hashtext('lc_asr_pipeline_retention_orphans')
                    ) AS locked
                    """
                )
            ).fetchone()
            if locked is None or locked["locked"] is not True:
                return len(orphans), 0
            for tenant_id, root_file_id in orphans:
                inserted = await connection.execute(
                    """
                    INSERT INTO storage_deletion_queue (
                        tenant_id, root_file_id, reason
                    )
                    SELECT %s, %s, 'orphan_scan'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM storage_deletion_queue
                        WHERE tenant_id = %s AND root_file_id = %s
                          AND completed_at IS NULL
                    )
                    """,
                    (tenant_id, root_file_id, tenant_id, root_file_id),
                )
                enqueued += inserted.rowcount
        await process_pending_storage_deletions(
            database,
            data_path=active_settings.data_path,
            limit=active_settings.retention_batch_limit,
        )
        return len(orphans), enqueued
    finally:
        await database.close()


async def run_retention_once(
    *,
    apply: bool,
    settings: Settings | None = None,
) -> dict[str, int]:
    active_settings = settings or get_settings()
    expired_batches, expired_files = await cleanup_expired(
        apply=apply,
        settings=active_settings,
    )
    orphan_candidates, orphan_enqueued = await scan_orphan_uploads(
        apply=apply,
        settings=active_settings,
    )
    deletion_summary = StorageDeletionSummary(completed=0, failed=0)
    if apply:
        database = Database(active_settings)
        await database.open()
        try:
            deletion_summary = await process_pending_storage_deletions(
                database,
                data_path=active_settings.data_path,
                limit=active_settings.retention_batch_limit,
            )
        finally:
            await database.close()
    return {
        "expired_batches": expired_batches,
        "expired_files": expired_files,
        "orphan_candidates": orphan_candidates,
        "orphan_enqueued": orphan_enqueued,
        "deletions_completed": deletion_summary.completed,
        "deletions_failed": deletion_summary.failed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run upload retention, deletion retries, and orphan checks"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply database/filesystem changes; default is a dry run",
    )
    arguments = parser.parse_args()
    summary = asyncio.run(run_retention_once(apply=arguments.apply))
    mode = "applied" if arguments.apply else "dry_run"
    fields = " ".join(f"{key}={value}" for key, value in summary.items())
    print(f"mode={mode} {fields}")


if __name__ == "__main__":
    main()
