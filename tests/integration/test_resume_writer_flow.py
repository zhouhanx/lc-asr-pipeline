"""PostgreSQL-backed resume writer flow and tenant boundary."""

from io import BytesIO
from uuid import UUID, uuid4

import httpx
import pytest
from PIL import Image

from lc_asr_pipeline.core.security import hash_password
from lc_asr_pipeline.main import app
from lc_asr_pipeline.repositories.identity import IdentityRepository


def _valid_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 24), (36, 87, 214)).save(output, format="PNG")
    return output.getvalue()


@pytest.mark.integration
async def test_resume_writer_source_edit_photo_export_and_isolation() -> None:
    suffix = uuid4().hex[:10]
    first_slug = f"resume-{suffix}"
    second_slug = f"resume-other-{suffix}"
    first_email = f"resume-{suffix}@example.com"
    second_email = f"resume-other-{suffix}@example.com"
    password = "Resume-Test-42!"

    async with app.router.lifespan_context(app):
        database = app.state.database
        async with database.system_connection() as connection:
            first = await IdentityRepository().register_tenant_owner(
                connection,
                tenant_slug=first_slug,
                tenant_name="Resume Writer Tenant",
                email=first_email,
                display_name="Resume Owner",
                password_hash=hash_password(password),
            )
            await IdentityRepository().register_tenant_owner(
                connection,
                tenant_slug=second_slug,
                tenant_name="Other Resume Tenant",
                email=second_email,
                display_name="Other Owner",
                password_hash=hash_password(password),
            )
            text_provider = await (
                await connection.execute(
                    """
                    INSERT INTO model_providers (
                        tenant_id, name, provider_type, model_kind, base_url,
                        model_name, api_key_ciphertext, capabilities
                    )
                    VALUES (
                        %s, 'Test text', 'deepseek', 'text',
                        'https://api.example.com', 'test-text', %s,
                        '["text_refinement"]'::jsonb
                    )
                    RETURNING id
                    """,
                    (first.tenant_id, b"test-only"),
                )
            ).fetchone()
            ocr_provider = await (
                await connection.execute(
                    """
                    SELECT id FROM model_providers
                    WHERE tenant_id = %s AND model_kind = 'ocr'
                    """,
                    (first.tenant_id,),
                )
            ).fetchone()
            assert text_provider is not None and ocr_provider is not None
            batch = await (
                await connection.execute(
                    """
                    INSERT INTO upload_batches (
                        tenant_id, created_by, name, total_bytes,
                        received_bytes, file_count, status
                    )
                    VALUES (%s, %s, 'Resume source', 100, 100, 1, 'ready')
                    RETURNING id
                    """,
                    (first.tenant_id, first.user_id),
                )
            ).fetchone()
            assert batch is not None
            uploaded_file = await (
                await connection.execute(
                    """
                    INSERT INTO uploaded_files (
                        batch_id, tenant_id, relative_path, original_name,
                        media_type, size_bytes, chunk_size, expected_chunks,
                        received_chunks, sha256, storage_path, status, file_kind
                    )
                    VALUES (
                        %s, %s, 'resumes/test-resume.pdf', 'test-resume.pdf',
                        'application/pdf', 100, 1048576, 1, 1,
                        %s, 'test/resume.pdf', 'ready', 'pdf'
                    )
                    RETURNING id
                    """,
                    (batch["id"], first.tenant_id, "a" * 64),
                )
            ).fetchone()
            assert uploaded_file is not None
            ocr_job = await (
                await connection.execute(
                    """
                    INSERT INTO ocr_jobs (
                        tenant_id, created_by, uploaded_file_id,
                        ocr_provider_id, text_provider_id,
                        ocr_provider_type_snapshot, ocr_base_url_snapshot,
                        ocr_model_name_snapshot, ocr_capabilities_snapshot,
                        text_provider_type_snapshot, text_base_url_snapshot,
                        text_model_name_snapshot,
                        text_api_key_ciphertext_snapshot,
                        text_capabilities_snapshot, document_kind,
                        file_attribute, status, progress_percent,
                        ocr_result_checkpoint, ocr_completed_at, completed_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        'paddleocr', 'https://ocr.example.com', 'test-ocr',
                        '{}'::jsonb, 'deepseek', 'https://api.example.com',
                        'test-text', %s, '{}'::jsonb, 'pdf', 'resume',
                        'completed', 100, '{}'::jsonb, now(), now()
                    )
                    RETURNING id
                    """,
                    (
                        first.tenant_id,
                        first.user_id,
                        uploaded_file["id"],
                        ocr_provider["id"],
                        text_provider["id"],
                        b"test-only",
                    ),
                )
            ).fetchone()
            assert ocr_job is not None
            ocr_result = await (
                await connection.execute(
                    """
                    INSERT INTO ocr_results (
                        tenant_id, job_id, uploaded_file_id, ocr_provider_id,
                        text_provider_id, markdown_text, page_count
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        '# 张三\\n\\n## 项目经历\\n语音平台', 1
                    )
                    RETURNING id
                    """,
                    (
                        first.tenant_id,
                        ocr_job["id"],
                        uploaded_file["id"],
                        ocr_provider["id"],
                        text_provider["id"],
                    ),
                )
            ).fetchone()
            assert ocr_result is not None
            profile = await (
                await connection.execute(
                    """
                    INSERT INTO resume_profiles (
                        tenant_id, ocr_job_id, ocr_result_id, uploaded_file_id,
                        candidate_name, phone, email,
                        extraction_model_name_snapshot, raw_profile
                    )
                    VALUES (
                        %s, %s, %s, %s, '张三', '13800000000',
                        'person@example.com', 'test-text',
                        %s::jsonb
                    )
                    RETURNING id
                    """,
                    (
                        first.tenant_id,
                        ocr_job["id"],
                        ocr_result["id"],
                        uploaded_file["id"],
                        (
                            '{"candidate_name":"张三","projects":['
                            '{"project_name":"语音平台","company_name":"LC",'
                            '"technologies":["FastAPI","PostgreSQL"],'
                            '"project_outcomes":["完成租户隔离"]}]}'
                        ),
                    ),
                )
            ).fetchone()
            assert profile is not None
            await connection.execute(
                """
                INSERT INTO resume_projects (
                    tenant_id, resume_profile_id, ocr_job_id, uploaded_file_id,
                    project_index, project_name, company_name,
                    responsibilities, technologies, raw_project
                )
                VALUES (
                    %s, %s, %s, %s, 0, '语音平台', 'LC',
                    ARRAY['完成租户隔离'], ARRAY['FastAPI', 'PostgreSQL'],
                    '{}'::jsonb
                )
                """,
                (
                    first.tenant_id,
                    profile["id"],
                    ocr_job["id"],
                    uploaded_file["id"],
                ),
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                first_login = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": first_slug,
                        "email": first_email,
                        "password": password,
                    },
                )
                second_login = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": second_slug,
                        "email": second_email,
                        "password": password,
                    },
                )
                assert first_login.status_code == 200
                assert second_login.status_code == 200
                first_headers = {"Authorization": f"Bearer {first_login.json()['access_token']}"}
                second_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}

                sources = await client.get(
                    "/api/v1/resume-writer/sources",
                    headers=first_headers,
                )
                assert sources.status_code == 200, sources.text
                assert len(sources.json()) == 1
                assert sources.json()[0]["candidate_name"] == "张三"
                searched = await client.get(
                    "/api/v1/resume-writer/sources?query=test-resume",
                    headers=first_headers,
                )
                assert len(searched.json()) == 1
                other_sources = await client.get(
                    "/api/v1/resume-writer/sources",
                    headers=second_headers,
                )
                assert other_sources.json() == []

                templates = await client.get(
                    "/api/v1/resume-writer/templates",
                    headers=first_headers,
                )
                assert templates.status_code == 200
                assert len(templates.json()) == 5
                assert all(item["group"] == "local" for item in templates.json())
                assert {item["key"] for item in templates.json()} == {
                    f"local-template-{index:02d}" for index in range(1, 6)
                }
                template_operation_id = templates.headers["x-operation-id"]
                UUID(template_operation_id.removeprefix("OP-"))

                created = await client.post(
                    "/api/v1/resume-writer/documents",
                    headers=first_headers,
                    json={
                        "source_resume_profile_id": sources.json()[0]["id"],
                        "template_key": "local-template-05",
                    },
                )
                assert created.status_code == 201, created.text
                document = created.json()
                document_id = document["id"]
                assert document["content"]["personal"]["name"] == "张三"
                assert document["content"]["projects"][0]["name"] == "语音平台"
                assert document["content"]["projects"][0]["source_project_id"] is not None
                assert "项目经历" in document["content"]["source_markdown"]

                duplicate = await client.post(
                    "/api/v1/resume-writer/documents",
                    headers=first_headers,
                    json={
                        "source_resume_profile_id": sources.json()[0]["id"],
                        "template_key": "local-template-01",
                    },
                )
                assert duplicate.json()["id"] == document_id
                cross_tenant = await client.get(
                    f"/api/v1/resume-writer/documents/{document_id}",
                    headers=second_headers,
                )
                assert cross_tenant.status_code == 404

                document["title"] = "张三平台工程师简历"
                document["theme_color"] = "#126B5B"
                document["content"]["personal"]["summary"] = "<script>unsafe</script>"
                for template in templates.json():
                    template_update = await client.put(
                        f"/api/v1/resume-writer/documents/{document_id}",
                        headers=first_headers,
                        json={
                            "title": document["title"],
                            "template_key": template["key"],
                            "theme_color": template["default_color"],
                            "content": document["content"],
                        },
                    )
                    assert template_update.status_code == 200, (
                        template["key"],
                        template_update.text,
                    )
                document["template_key"] = "local-template-05"
                updated = await client.put(
                    f"/api/v1/resume-writer/documents/{document_id}",
                    headers=first_headers,
                    json={
                        "title": document["title"],
                        "template_key": document["template_key"],
                        "theme_color": document["theme_color"],
                        "content": document["content"],
                    },
                )
                assert updated.status_code == 200, updated.text

                invalid_photo = await client.put(
                    f"/api/v1/resume-writer/documents/{document_id}/photo",
                    headers={**first_headers, "Content-Type": "image/png"},
                    content=b"not-a-png",
                )
                assert invalid_photo.status_code == 422
                valid_photo = await client.put(
                    f"/api/v1/resume-writer/documents/{document_id}/photo",
                    headers={**first_headers, "Content-Type": "image/png"},
                    content=_valid_png(),
                )
                assert valid_photo.status_code == 204
                photo = await client.get(
                    f"/api/v1/resume-writer/documents/{document_id}/photo",
                    headers=first_headers,
                )
                assert photo.status_code == 200
                assert photo.headers["content-type"] == "image/png"

                html_export = await client.get(
                    f"/api/v1/resume-writer/documents/{document_id}/export/html",
                    headers=first_headers,
                )
                assert html_export.status_code == 200, html_export.text
                assert "<script>unsafe</script>" not in html_export.text
                assert "&lt;script&gt;unsafe&lt;/script&gt;" in html_export.text
                assert "data:image/png;base64," in html_export.text

                pdf_export = await client.get(
                    f"/api/v1/resume-writer/documents/{document_id}/export/pdf",
                    headers=first_headers,
                )
                assert pdf_export.status_code == 200, pdf_export.text
                assert pdf_export.headers["content-type"] == "application/pdf"
                assert pdf_export.content.startswith(b"%PDF-")

                removed_photo = await client.delete(
                    f"/api/v1/resume-writer/documents/{document_id}/photo",
                    headers=first_headers,
                )
                assert removed_photo.status_code == 204

                cross_tenant_delete = await client.delete(
                    f"/api/v1/resume-writer/documents/{document_id}",
                    headers=second_headers,
                )
                assert cross_tenant_delete.status_code == 404
                deleted_document = await client.delete(
                    f"/api/v1/resume-writer/documents/{document_id}",
                    headers=first_headers,
                )
                assert deleted_document.status_code == 204
                delete_operation_id = deleted_document.headers["x-operation-id"]
                UUID(delete_operation_id.removeprefix("OP-"))
                assert delete_operation_id != template_operation_id
                missing_document = await client.get(
                    f"/api/v1/resume-writer/documents/{document_id}",
                    headers=first_headers,
                )
                assert missing_document.status_code == 404
                repeated_delete = await client.delete(
                    f"/api/v1/resume-writer/documents/{document_id}",
                    headers=first_headers,
                )
                assert repeated_delete.status_code == 404
                remaining_documents = await client.get(
                    "/api/v1/resume-writer/documents",
                    headers=first_headers,
                )
                assert remaining_documents.json() == []
                sources_after_delete = await client.get(
                    "/api/v1/resume-writer/sources",
                    headers=first_headers,
                )
                assert sources_after_delete.json()[0]["draft_id"] is None
            finally:
                async with database.system_connection() as connection:
                    await connection.execute(
                        "DELETE FROM tenants WHERE slug IN (%s, %s)",
                        (first_slug, second_slug),
                    )
                    await connection.execute(
                        "DELETE FROM users WHERE normalized_email IN (%s, %s)",
                        (first_email, second_email),
                    )
