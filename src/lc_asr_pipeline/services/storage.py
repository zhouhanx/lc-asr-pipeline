"""Safe physical-storage deletion helpers."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

from lc_asr_pipeline.db.pool import Database


@dataclass(frozen=True, slots=True)
class StorageDeletionSummary:
    completed: int
    failed: int


def delete_uploaded_file_storage(
    *,
    data_path: Path,
    tenant_id: UUID,
    root_file_id: UUID | None,
    exact_storage_path: str | None,
) -> None:
    """Delete only paths proven to be below the current tenant upload root."""
    tenant_root = (data_path.resolve() / "uploads" / str(tenant_id)).resolve()
    if root_file_id is not None:
        root = (tenant_root / str(root_file_id)).resolve()
        if not root.is_relative_to(tenant_root):
            raise ValueError("Upload storage target escaped the tenant root")
        if root.exists():
            shutil.rmtree(root)
        return
    if exact_storage_path is None:
        return
    target = Path(exact_storage_path).resolve()
    if not target.is_relative_to(tenant_root):
        raise ValueError("Upload storage target escaped the tenant root")
    target.unlink(missing_ok=True)
    parent = target.parent
    while parent != tenant_root and parent.is_relative_to(tenant_root):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


async def process_pending_storage_deletions(
    database: Database,
    *,
    data_path: Path,
    limit: int,
    deletion_ids: list[int] | None = None,
) -> StorageDeletionSummary:
    """Claim queued deletions and persist retry state for filesystem failures."""
    completed = 0
    failed = 0
    async with database.system_connection() as connection:
        rows = await (
            await connection.execute(
                """
                SELECT id, tenant_id, root_file_id, exact_storage_path, attempts
                FROM storage_deletion_queue
                WHERE completed_at IS NULL
                  AND next_attempt_at <= now()
                  AND (%s::bigint[] IS NULL OR id = ANY(%s::bigint[]))
                ORDER BY next_attempt_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (deletion_ids, deletion_ids, limit),
            )
        ).fetchall()
        for row in rows:
            deletion_id = cast(int, row["id"])
            try:
                delete_uploaded_file_storage(
                    data_path=data_path,
                    tenant_id=cast(UUID, row["tenant_id"]),
                    root_file_id=cast(UUID | None, row["root_file_id"]),
                    exact_storage_path=(
                        str(row["exact_storage_path"])
                        if row["exact_storage_path"] is not None
                        else None
                    ),
                )
            except (OSError, ValueError) as error:
                attempts = cast(int, row["attempts"]) + 1
                retry_seconds = min(3600, 30 * (2 ** min(attempts - 1, 7)))
                await connection.execute(
                    """
                    UPDATE storage_deletion_queue
                    SET attempts = %s,
                        next_attempt_at = now() + make_interval(secs => %s),
                        last_error_type = %s
                    WHERE id = %s
                    """,
                    (attempts, retry_seconds, type(error).__name__, deletion_id),
                )
                failed += 1
            else:
                await connection.execute(
                    """
                    UPDATE storage_deletion_queue
                    SET attempts = attempts + 1, completed_at = now(),
                        last_error_type = NULL
                    WHERE id = %s
                    """,
                    (deletion_id,),
                )
                completed += 1
    return StorageDeletionSummary(completed=completed, failed=failed)
