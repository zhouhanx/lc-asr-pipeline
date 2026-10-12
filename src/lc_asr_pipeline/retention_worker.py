"""Periodic retention worker for upload staging and storage deletion retries."""

from __future__ import annotations

import asyncio
import logging

from lc_asr_pipeline.cleanup import run_retention_once
from lc_asr_pipeline.core.config import get_settings

logger = logging.getLogger(__name__)


async def run_forever() -> None:
    settings = get_settings()
    while True:
        try:
            summary = await run_retention_once(apply=True)
            logger.info(
                "event=retention_cycle_complete expired_batches=%d expired_files=%d "
                "orphan_candidates=%d orphan_enqueued=%d deletions_completed=%d "
                "deletions_failed=%d",
                summary["expired_batches"],
                summary["expired_files"],
                summary["orphan_candidates"],
                summary["orphan_enqueued"],
                summary["deletions_completed"],
                summary["deletions_failed"],
            )
        except Exception as error:
            logger.error(
                "event=retention_cycle_failed error_type=%s",
                type(error).__name__,
            )
        await asyncio.sleep(settings.retention_scan_interval_seconds)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
