"""Tenant-scoped resume authoring persistence."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from lc_asr_pipeline.schemas.resume_writer import (
    ResumeContent,
    ResumeDocumentUpdate,
    ResumePersonalInfo,
    ResumeProjectEntry,
)


class ResumeWriterRepository:
    @staticmethod
    def _document_query(where: str) -> str:
        return f"""
            SELECT document.id, document.source_resume_profile_id,
                   file.relative_path AS source_path, document.title,
                   document.template_key, document.theme_color, document.content,
                   (photo.resume_document_id IS NOT NULL) AS has_photo,
                   document.created_at, document.updated_at
            FROM resume_documents document
            LEFT JOIN resume_profiles profile
              ON profile.id = document.source_resume_profile_id
            LEFT JOIN uploaded_files file ON file.id = profile.uploaded_file_id
            LEFT JOIN resume_document_photos photo
              ON photo.resume_document_id = document.id
            {where}
        """

    async def list_sources(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        query: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        search = query.strip() if query else ""
        cursor = await connection.execute(
            """
            SELECT profile.id, profile.candidate_name,
                   file.relative_path AS source_path, profile.extracted_at,
                   count(project.id)::integer AS project_count,
                   document.id AS draft_id
            FROM resume_profiles profile
            JOIN uploaded_files file ON file.id = profile.uploaded_file_id
            LEFT JOIN resume_projects project
              ON project.resume_profile_id = profile.id
            LEFT JOIN resume_documents document
              ON document.tenant_id = profile.tenant_id
             AND document.source_resume_profile_id = profile.id
            WHERE profile.tenant_id = %s
              AND (
                %s = ''
                OR profile.candidate_name ILIKE ('%%' || %s || '%%')
                OR file.relative_path ILIKE ('%%' || %s || '%%')
              )
            GROUP BY profile.id, file.relative_path, document.id
            ORDER BY profile.extracted_at DESC
            LIMIT %s
            """,
            (tenant_id, search, search, search, limit),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def list_documents(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            self._document_query(
                "WHERE document.tenant_id = %s ORDER BY document.updated_at DESC LIMIT 100"
            ),
            (tenant_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_document(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                self._document_query("WHERE document.id = %s AND document.tenant_id = %s"),
                (document_id, tenant_id),
            )
        ).fetchone()
        return None if row is None else dict(row)

    async def create_document(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        user_id: UUID,
        source_profile_id: UUID | None,
        template_key: str,
    ) -> dict[str, Any] | None:
        title = "未命名简历"
        content = ResumeContent()
        if source_profile_id is not None:
            source = await (
                await connection.execute(
                    """
                    SELECT profile.candidate_name, profile.phone, profile.email,
                           result.markdown_text
                    FROM resume_profiles profile
                    JOIN ocr_results result ON result.id = profile.ocr_result_id
                    WHERE profile.id = %s AND profile.tenant_id = %s
                    """,
                    (source_profile_id, tenant_id),
                )
            ).fetchone()
            if source is None:
                return None
            candidate_name = str(source["candidate_name"])
            title = f"{candidate_name}的简历"
            project_cursor = await connection.execute(
                """
                SELECT id, project_name, company_name, role_name,
                       start_date_text, end_date_text, is_current,
                       description, responsibilities, technologies,
                       project_background, project_responsibilities,
                       project_outcomes
                FROM resume_projects
                WHERE resume_profile_id = %s AND tenant_id = %s
                ORDER BY project_index
                """,
                (source_profile_id, tenant_id),
            )
            source_projects = await project_cursor.fetchall()
            projects: list[ResumeProjectEntry] = []
            for raw in source_projects:
                highlight_values = cast(
                    list[object],
                    raw["project_outcomes"]
                    or raw["project_responsibilities"]
                    or raw["responsibilities"]
                    or [],
                )
                highlights = [str(item) for item in highlight_values if item]
                projects.append(
                    ResumeProjectEntry(
                        id=uuid4().hex,
                        source_project_id=cast(UUID, raw["id"]),
                        name=str(raw["project_name"] or ""),
                        company=str(raw["company_name"] or ""),
                        role=str(raw["role_name"] or ""),
                        start_date=str(raw["start_date_text"] or ""),
                        end_date=("至今" if raw["is_current"] else str(raw["end_date_text"] or "")),
                        summary=str(raw["project_background"] or raw["description"] or ""),
                        highlights=highlights,
                        technologies=[
                            str(item)
                            for item in cast(list[object], raw["technologies"] or [])
                            if item
                        ],
                    )
                )
            content = ResumeContent(
                personal=ResumePersonalInfo(
                    name=candidate_name,
                    phone=str(source["phone"] or ""),
                    email=str(source["email"] or ""),
                ),
                projects=projects,
                source_markdown=str(source["markdown_text"]),
            )
        inserted = await (
            await connection.execute(
                """
                INSERT INTO resume_documents (
                    tenant_id, created_by, source_resume_profile_id,
                    title, template_key, content
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, source_resume_profile_id)
                    WHERE source_resume_profile_id IS NOT NULL
                DO UPDATE SET updated_at = resume_documents.updated_at
                RETURNING id
                """,
                (
                    tenant_id,
                    user_id,
                    source_profile_id,
                    title,
                    template_key,
                    Jsonb(content.model_dump(mode="json")),
                ),
            )
        ).fetchone()
        assert inserted is not None
        return await self.get_document(
            connection,
            tenant_id=tenant_id,
            document_id=inserted["id"],  # type: ignore[arg-type]
        )

    async def update_document(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        document_id: UUID,
        update: ResumeDocumentUpdate,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                """
                UPDATE resume_documents
                SET title = %s, template_key = %s, theme_color = %s,
                    content = %s, updated_at = now()
                WHERE id = %s AND tenant_id = %s
                RETURNING id
                """,
                (
                    update.title,
                    update.template_key,
                    update.theme_color,
                    Jsonb(update.content.model_dump(mode="json")),
                    document_id,
                    tenant_id,
                ),
            )
        ).fetchone()
        if row is None:
            return None
        return await self.get_document(
            connection,
            tenant_id=tenant_id,
            document_id=document_id,
        )

    async def delete_document(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> bool:
        """Delete one tenant-owned draft and its cascading dependent rows."""
        row = await (
            await connection.execute(
                """
                DELETE FROM resume_documents
                WHERE id = %s AND tenant_id = %s
                RETURNING id
                """,
                (document_id, tenant_id),
            )
        ).fetchone()
        return row is not None

    async def put_photo(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        document_id: UUID,
        media_type: str,
        image_bytes: bytes,
    ) -> bool:
        owned = await (
            await connection.execute(
                "SELECT 1 FROM resume_documents WHERE id = %s AND tenant_id = %s",
                (document_id, tenant_id),
            )
        ).fetchone()
        if owned is None:
            return False
        await connection.execute(
            """
            INSERT INTO resume_document_photos (
                tenant_id, resume_document_id, media_type, image_bytes
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (resume_document_id)
            DO UPDATE SET tenant_id = EXCLUDED.tenant_id,
                          media_type = EXCLUDED.media_type,
                          image_bytes = EXCLUDED.image_bytes,
                          updated_at = now()
            """,
            (tenant_id, document_id, media_type, image_bytes),
        )
        await connection.execute(
            "UPDATE resume_documents SET updated_at = now() WHERE id = %s",
            (document_id,),
        )
        return True

    async def get_photo(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> tuple[str, bytes] | None:
        row = await (
            await connection.execute(
                """
                SELECT photo.media_type, photo.image_bytes
                FROM resume_document_photos photo
                JOIN resume_documents document
                  ON document.id = photo.resume_document_id
                WHERE document.id = %s AND document.tenant_id = %s
                """,
                (document_id, tenant_id),
            )
        ).fetchone()
        if row is None:
            return None
        return str(row["media_type"]), cast(bytes, row["image_bytes"])

    async def delete_photo(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        document_id: UUID,
    ) -> bool:
        row = await (
            await connection.execute(
                """
                DELETE FROM resume_document_photos photo
                USING resume_documents document
                WHERE photo.resume_document_id = document.id
                  AND document.id = %s AND document.tenant_id = %s
                RETURNING photo.resume_document_id
                """,
                (document_id, tenant_id),
            )
        ).fetchone()
        return row is not None
