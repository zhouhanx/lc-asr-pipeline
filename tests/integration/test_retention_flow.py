"""Retention scheduling, deletion retries, and guarded orphan scanning."""

from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from lc_asr_pipeline.cleanup import cleanup_expired, scan_orphan_uploads
from lc_asr_pipeline.core.config import get_settings
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.services.storage import process_pending_storage_deletions


@pytest.mark.integration
async def test_retention_queue_recovers_failures_and_deletes_only_safe_orphans(
    tmp_path: Path,
) -> None:
    settings = get_settings().model_copy(
        update={
            "data_path": tmp_path,
            "retention_batch_limit": 50,
            "retention_orphan_grace_seconds": 300,
        }
    )
    database = Database(settings)
    await database.open()
    suffix = uuid4().hex[:10]
    tenant_id: UUID | None = None
    try:
        async with database.system_connection() as connection:
            tenant = await (
                await connection.execute(
                    """
                    INSERT INTO tenants (slug, name)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (f"retention-{suffix}", f"Retention {suffix}"),
                )
            ).fetchone()
            assert tenant is not None
            tenant_id = tenant["id"]  # type: ignore[assignment]
            user = await (
                await connection.execute(
                    """
                    INSERT INTO users (
                        email, normalized_email, display_name, password_hash
                    )
                    VALUES (%s, %s, 'Retention Test', 'not-used')
                    RETURNING id
                    """,
                    (f"retention-{suffix}@example.com", f"retention-{suffix}@example.com"),
                )
            ).fetchone()
            assert user is not None
            batch = await (
                await connection.execute(
                    """
                    INSERT INTO upload_batches (
                        tenant_id, created_by, name, total_bytes, file_count,
                        status, expires_at
                    )
                    VALUES (%s, %s, 'Expired', 1, 1, 'failed',
                            now() - interval '1 hour')
                    RETURNING id
                    """,
                    (tenant_id, user["id"]),
                )
            ).fetchone()
            assert batch is not None
            expired_file = await (
                await connection.execute(
                    """
                    INSERT INTO uploaded_files (
                        batch_id, tenant_id, relative_path, original_name,
                        size_bytes, chunk_size, expected_chunks, status
                    )
                    VALUES (%s, %s, 'expired.wav', 'expired.wav',
                            1, 1048576, 1, 'failed')
                    RETURNING id
                    """,
                    (batch["id"], tenant_id),
                )
            ).fetchone()
            assert expired_file is not None

        expired_root = tmp_path / "uploads" / str(tenant_id) / str(expired_file["id"])
        expired_root.mkdir(parents=True)
        (expired_root / "partial.bin").write_bytes(b"x")
        expired_batches, expired_files = await cleanup_expired(
            apply=True,
            settings=settings,
        )
        assert (expired_batches, expired_files) == (1, 1)
        assert not expired_root.exists()
        async with database.system_connection() as connection:
            queue_state = await (
                await connection.execute(
                    """
                    SELECT completed_at IS NOT NULL AS completed
                    FROM storage_deletion_queue
                    WHERE tenant_id = %s AND reason = 'expired_upload'
                    ORDER BY id DESC LIMIT 1
                    """,
                    (tenant_id,),
                )
            ).fetchone()
            assert queue_state is not None and queue_state["completed"] is True

        outside = tmp_path / "outside"
        outside.mkdir()
        sentinel = outside / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        unsafe_id = uuid4()
        unsafe_link = tmp_path / "uploads" / str(tenant_id) / str(unsafe_id)
        unsafe_link.symlink_to(outside, target_is_directory=True)
        async with database.system_connection() as connection:
            failed_queue = await (
                await connection.execute(
                    """
                    INSERT INTO storage_deletion_queue (
                        tenant_id, root_file_id, reason
                    )
                    VALUES (%s, %s, 'orphan_scan')
                    RETURNING id
                    """,
                    (tenant_id, unsafe_id),
                )
            ).fetchone()
            assert failed_queue is not None
        failed = await process_pending_storage_deletions(
            database,
            data_path=tmp_path,
            limit=1,
            deletion_ids=[int(failed_queue["id"])],
        )
        assert failed.failed == 1
        assert sentinel.read_text(encoding="utf-8") == "keep"
        async with database.system_connection() as connection:
            retry_state = await (
                await connection.execute(
                    """
                    SELECT attempts, completed_at, last_error_type
                    FROM storage_deletion_queue WHERE id = %s
                    """,
                    (failed_queue["id"],),
                )
            ).fetchone()
            assert retry_state is not None
            assert retry_state["attempts"] == 1
            assert retry_state["completed_at"] is None
            assert retry_state["last_error_type"] == "ValueError"
        unsafe_link.unlink()

        async with database.system_connection() as connection:
            active_batch = await (
                await connection.execute(
                    """
                    INSERT INTO upload_batches (
                        tenant_id, created_by, name, total_bytes, file_count, status
                    )
                    VALUES (%s, %s, 'Active', 1, 1, 'ready')
                    RETURNING id
                    """,
                    (tenant_id, user["id"]),
                )
            ).fetchone()
            assert active_batch is not None
            referenced = await (
                await connection.execute(
                    """
                    INSERT INTO uploaded_files (
                        batch_id, tenant_id, relative_path, original_name,
                        size_bytes, chunk_size, expected_chunks, received_chunks,
                        status, storage_path
                    )
                    VALUES (%s, %s, 'active.wav', 'active.wav',
                            1, 1048576, 1, 1, 'ready', 'placeholder')
                    RETURNING id
                    """,
                    (active_batch["id"], tenant_id),
                )
            ).fetchone()
            assert referenced is not None

        tenant_root = tmp_path / "uploads" / str(tenant_id)
        orphan_id = uuid4()
        recent_id = uuid4()
        orphan_root = tenant_root / str(orphan_id)
        recent_root = tenant_root / str(recent_id)
        referenced_root = tenant_root / str(referenced["id"])
        invalid_root = tenant_root / "not-a-uuid"
        for path in (orphan_root, recent_root, referenced_root, invalid_root):
            path.mkdir()
            (path / "data.bin").write_bytes(b"x")
        old_time = time.time() - 600
        for path in (orphan_root, referenced_root, invalid_root):
            os.utime(path, (old_time, old_time))

        dry_candidates, dry_enqueued = await scan_orphan_uploads(
            apply=False,
            settings=settings,
        )
        assert (dry_candidates, dry_enqueued) == (1, 0)
        candidates, enqueued = await scan_orphan_uploads(
            apply=True,
            settings=settings,
        )
        assert (candidates, enqueued) == (1, 1)
        assert not orphan_root.exists()
        assert recent_root.exists()
        assert referenced_root.exists()
        assert invalid_root.exists()
    finally:
        if tenant_id is not None:
            async with database.system_connection() as connection:
                await connection.execute(
                    "DELETE FROM storage_deletion_queue WHERE tenant_id = %s",
                    (tenant_id,),
                )
                await connection.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
                await connection.execute(
                    "DELETE FROM users WHERE normalized_email = %s",
                    (f"retention-{suffix}@example.com",),
                )
        await database.close()
