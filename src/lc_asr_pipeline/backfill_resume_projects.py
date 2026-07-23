"""Backfill structured projects for completed resume OCR results."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any
from uuid import UUID

from lc_asr_pipeline.core.config import get_settings
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.repositories.resume_projects import ResumeProjectRepository
from lc_asr_pipeline.schemas.resume_project import ResumeProjectExtractionRequest
from lc_asr_pipeline.services.model_secrets import decrypt_model_secret
from lc_asr_pipeline.services.network_policy import enforce_provider_network_policy
from lc_asr_pipeline.services.resume_project_extraction import (
    ResumeProjectExtractor,
    build_resume_project_extraction_chain,
)


async def _jobs_to_process(
    database: Database,
    *,
    refresh: bool,
) -> list[dict[str, Any]]:
    async with database.connection() as connection:
        cursor = await connection.execute(
            """
            SELECT job.id, job.tenant_id, job.uploaded_file_id,
                   job.text_provider_type_snapshot,
                   job.text_base_url_snapshot,
                   job.text_model_name_snapshot,
                   job.text_api_key_ciphertext_snapshot,
                   result.id AS ocr_result_id, result.markdown_text
            FROM ocr_jobs job
            JOIN ocr_results result ON result.job_id = job.id
            LEFT JOIN resume_profiles profile ON profile.ocr_job_id = job.id
            WHERE job.file_attribute = 'resume'
              AND job.status = 'completed'
              AND (%s OR profile.id IS NULL)
            ORDER BY job.completed_at
            """,
            (refresh,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def backfill_resume_projects(*, refresh: bool = False) -> tuple[int, int]:
    settings = get_settings()
    database = Database(settings)
    repository = ResumeProjectRepository()
    await database.open()
    completed = 0
    project_count = 0
    try:
        for row in await _jobs_to_process(database, refresh=refresh):
            tenant_id: UUID = row["tenant_id"]
            api_key = decrypt_model_secret(
                row["text_api_key_ciphertext_snapshot"],
                master_secret=settings.model_secret_key,
                tenant_id=tenant_id,
            )
            base_url = str(row["text_base_url_snapshot"])
            provider_type = str(row["text_provider_type_snapshot"])
            await enforce_provider_network_policy(
                base_url,
                trusted_hosts=({"api.deepseek.com"} if provider_type == "deepseek" else ()),
            )
            extractor = ResumeProjectExtractor(
                api_key=api_key,
                base_url=base_url,
                model=str(row["text_model_name_snapshot"]),
                timeout_seconds=settings.text_model_request_timeout_seconds,
                provider_type=provider_type,
            )
            extraction = await build_resume_project_extraction_chain(extractor).ainvoke(
                ResumeProjectExtractionRequest(markdown_text=str(row["markdown_text"]))
            )
            async with database.connection() as connection:
                await repository.replace_extraction(
                    connection,
                    tenant_id=tenant_id,
                    ocr_job_id=row["id"],
                    ocr_result_id=row["ocr_result_id"],
                    uploaded_file_id=row["uploaded_file_id"],
                    extraction=extraction,
                )
            completed += 1
            project_count += len(extraction.projects)
        return completed, project_count
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-extract profiles that already have stored projects.",
    )
    arguments = parser.parse_args()
    resumes, projects = asyncio.run(backfill_resume_projects(refresh=arguments.refresh))
    print(f"Backfilled resume profiles: {resumes}; projects: {projects}")


if __name__ == "__main__":
    main()
