"""Retention cleanup for expired, non-active upload staging data."""

from __future__ import annotations

import argparse
import asyncio
import shutil
from collections import defaultdict
from typing import cast
from uuid import UUID

from lc_asr_pipeline.core.config import get_settings
from lc_asr_pipeline.db.pool import Database


async def cleanup_expired(*, apply: bool) -> tuple[int, int]:
    settings = get_settings()
    database = Database(settings)
    await database.open()
    try:
        async with database.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT b.id AS batch_id, b.tenant_id, f.id AS file_id
                FROM upload_batches b
                LEFT JOIN uploaded_files f ON f.batch_id = b.id
                WHERE b.expires_at <= now()
                  AND b.status IN ('uploading', 'cancelled', 'failed')
                ORDER BY b.id
                """
            )
            rows = await cursor.fetchall()
        batches: dict[tuple[UUID, UUID], list[UUID]] = defaultdict(list)
        for row in rows:
            key = (cast(UUID, row["tenant_id"]), cast(UUID, row["batch_id"]))
            if row["file_id"] is not None:
                batches[key].append(cast(UUID, row["file_id"]))
        if not apply:
            return len(batches), sum(len(files) for files in batches.values())
        deleted_files = 0
        for (tenant_id, batch_id), file_ids in batches.items():
            for file_id in file_ids:
                target = (
                    settings.data_path.resolve()
                    / "uploads"
                    / str(tenant_id)
                    / str(file_id)
                )
                shutil.rmtree(target, ignore_errors=True)
                deleted_files += 1
            async with database.connection() as connection:
                await connection.execute(
                    """
                    DELETE FROM upload_batches
                    WHERE id = %s AND tenant_id = %s AND expires_at <= now()
                      AND status IN ('uploading', 'cancelled', 'failed')
                    """,
                    (batch_id, tenant_id),
                )
        return len(batches), deleted_files
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean expired upload staging data")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="delete expired rows/files; without this flag the command is a dry run",
    )
    arguments = parser.parse_args()
    batches, files = asyncio.run(cleanup_expired(apply=arguments.apply))
    mode = "deleted" if arguments.apply else "would_delete"
    print(f"{mode}_batches={batches} {mode}_files={files}")


if __name__ == "__main__":
    main()
