"""Tenant-scoped resume profile and project persistence."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from lc_asr_pipeline.schemas.resume_project import ResumeProjectExtraction


class ResumeProjectRepository:
    async def replace_extraction(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        ocr_job_id: UUID,
        ocr_result_id: UUID,
        uploaded_file_id: UUID,
        extraction: ResumeProjectExtraction,
    ) -> UUID:
        profile = await (
            await connection.execute(
                """
                INSERT INTO resume_profiles (
                    tenant_id, ocr_job_id, ocr_result_id, uploaded_file_id,
                    candidate_name, phone, email, current_company,
                    extraction_model_name_snapshot, raw_profile
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ocr_job_id)
                DO UPDATE SET
                    ocr_result_id = EXCLUDED.ocr_result_id,
                    uploaded_file_id = EXCLUDED.uploaded_file_id,
                    candidate_name = EXCLUDED.candidate_name,
                    phone = EXCLUDED.phone,
                    email = EXCLUDED.email,
                    current_company = EXCLUDED.current_company,
                    extraction_model_name_snapshot =
                        EXCLUDED.extraction_model_name_snapshot,
                    raw_profile = EXCLUDED.raw_profile,
                    extracted_at = now(),
                    updated_at = now()
                RETURNING id
                """,
                (
                    tenant_id,
                    ocr_job_id,
                    ocr_result_id,
                    uploaded_file_id,
                    extraction.candidate_name,
                    extraction.phone,
                    extraction.email,
                    extraction.current_company,
                    extraction.model,
                    Jsonb(extraction.model_dump(mode="json")),
                ),
            )
        ).fetchone()
        assert profile is not None
        profile_id: UUID = profile["id"]  # type: ignore[assignment]
        await connection.execute(
            "DELETE FROM resume_projects WHERE resume_profile_id = %s",
            (profile_id,),
        )
        for index, project in enumerate(extraction.projects):
            await connection.execute(
                """
                INSERT INTO resume_projects (
                    tenant_id, resume_profile_id, ocr_job_id, uploaded_file_id,
                    project_index, project_name, company_name, role_name,
                    start_date_text, end_date_text, is_current, description,
                    responsibilities, technologies, project_background,
                    project_responsibilities, project_outcomes,
                    architecture_score, architecture_reason,
                    credibility_score, credibility_reason,
                    embellishment_risk_score, embellishment_risk_reason,
                    source_excerpt, raw_project
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s
                )
                """,
                (
                    tenant_id,
                    profile_id,
                    ocr_job_id,
                    uploaded_file_id,
                    index,
                    project.project_name,
                    project.company_name,
                    project.role_name,
                    project.start_date,
                    project.end_date,
                    project.is_current,
                    project.description,
                    project.responsibilities,
                    project.technologies,
                    project.project_background,
                    project.project_responsibilities,
                    project.project_outcomes,
                    project.scoring.architecture_rationality.score,
                    project.scoring.architecture_rationality.reason,
                    project.scoring.description_credibility.score,
                    project.scoring.description_credibility.reason,
                    project.scoring.embellishment_risk.score,
                    project.scoring.embellishment_risk.reason,
                    project.source_excerpt,
                    Jsonb(project.model_dump(mode="json")),
                ),
            )
        return profile_id

    async def list_for_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT project.id, project.resume_profile_id, project.ocr_job_id,
                   project.uploaded_file_id, profile.candidate_name,
                   profile.phone, profile.email, project.project_index,
                   project.project_name, project.company_name, project.role_name,
                   project.start_date_text AS start_date,
                   project.end_date_text AS end_date, project.is_current,
                   project.description, project.responsibilities,
                   project.technologies, project.project_background,
                   project.project_responsibilities, project.project_outcomes,
                   project.architecture_score, project.architecture_reason,
                   project.credibility_score, project.credibility_reason,
                   project.embellishment_risk_score,
                   project.embellishment_risk_reason,
                   project.overall_score::float AS overall_score,
                   project.source_excerpt,
                   file.relative_path AS source_path,
                   profile.extraction_model_name_snapshot AS extraction_model_name,
                   job.ocr_completed_at, profile.extracted_at
            FROM resume_projects project
            JOIN resume_profiles profile ON profile.id = project.resume_profile_id
            JOIN ocr_jobs job ON job.id = project.ocr_job_id
            JOIN uploaded_files file ON file.id = project.uploaded_file_id
            WHERE project.tenant_id = %s
            ORDER BY profile.extracted_at DESC, project.project_index
            LIMIT 1000
            """,
            (tenant_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_for_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        project_id: UUID,
    ) -> dict[str, Any] | None:
        rows = await self.list_for_tenant(connection, tenant_id=tenant_id)
        return next((row for row in rows if row["id"] == project_id), None)

    async def summary(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
    ) -> dict[str, int]:
        row = await (
            await connection.execute(
                """
                SELECT count(*)::integer AS project_count,
                       (
                           SELECT count(*)::integer
                           FROM resume_profiles profile
                           WHERE profile.tenant_id = %s
                       ) AS candidate_count,
                       count(DISTINCT company_name)
                           FILTER (WHERE company_name IS NOT NULL)::integer
                           AS company_count
                FROM resume_projects
                WHERE tenant_id = %s
                """,
                (tenant_id, tenant_id),
            )
        ).fetchone()
        assert row is not None
        return {
            "project_count": int(str(row["project_count"])),
            "candidate_count": int(str(row["candidate_count"])),
            "company_count": int(str(row["company_count"])),
        }
