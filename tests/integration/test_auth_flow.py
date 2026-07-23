"""PostgreSQL-backed tenant authentication flow tests."""

import hashlib
import io
import shutil
import zipfile
from uuid import uuid4

import httpx
import pytest

from lc_asr_pipeline.core.security import hash_password
from lc_asr_pipeline.main import app
from lc_asr_pipeline.worker import recover_stale_jobs


@pytest.mark.integration
async def test_tenant_registration_login_refresh_and_isolation() -> None:
    suffix = uuid4().hex[:12]
    tenant_slug = f"tenant-{suffix}"
    second_tenant_slug = f"other-{suffix}"
    email = f"owner-{suffix}@example.com"
    member_email = f"member-{suffix}@example.com"
    second_email = f"other-{suffix}@example.com"
    password = "Correct-Horse-42!"
    second_password = "Other-Correct-Horse-42!"
    second_updated_password = "Abcdefg1"
    second_reset_password = "ResetPass1"
    admin_username = f"admin-{suffix}"
    admin_password = "Admin-Correct-Horse-42!"
    admin_new_password = "Admin-New-Correct-Horse-42!"
    admin_final_password = "Admin-Final-Correct-Horse-42!"

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            try:
                database = app.state.database
                async with database.connection() as connection:
                    await connection.execute(
                        """
                        INSERT INTO platform_admins (
                            username, password_hash, must_change_password
                        ) VALUES (%s, %s, true)
                        """,
                        (admin_username, hash_password(admin_password)),
                    )
                admin_login = await client.post(
                    "/api/v1/admin/auth/login",
                    json={"username": admin_username, "password": admin_password},
                )
                assert admin_login.status_code == 200, admin_login.text
                assert admin_login.json()["password_change_required"] is True
                initial_admin_token = admin_login.json()["access_token"]
                blocked_admin = await client.get(
                    "/api/v1/admin/tenants",
                    headers={"Authorization": f"Bearer {initial_admin_token}"},
                )
                assert blocked_admin.status_code == 401
                changed_admin = await client.post(
                    "/api/v1/admin/auth/change-initial-password",
                    headers={"Authorization": f"Bearer {initial_admin_token}"},
                    json={"new_password": admin_new_password},
                )
                assert changed_admin.status_code == 204, changed_admin.text
                stale_admin_token = await client.get(
                    "/api/v1/admin/tenants",
                    headers={"Authorization": f"Bearer {initial_admin_token}"},
                )
                assert stale_admin_token.status_code == 401
                admin_login = await client.post(
                    "/api/v1/admin/auth/login",
                    json={"username": admin_username, "password": admin_new_password},
                )
                assert admin_login.status_code == 200
                assert admin_login.json()["password_change_required"] is False
                admin_token = admin_login.json()["access_token"]
                wrong_admin_password = await client.post(
                    "/api/v1/admin/auth/change-password",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "current_password": "wrong-admin-password",
                        "new_password": admin_final_password,
                    },
                )
                assert wrong_admin_password.status_code == 400
                changed_admin_password = await client.post(
                    "/api/v1/admin/auth/change-password",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "current_password": admin_new_password,
                        "new_password": admin_final_password,
                    },
                )
                assert changed_admin_password.status_code == 204
                obsolete_admin_login = await client.post(
                    "/api/v1/admin/auth/login",
                    json={"username": admin_username, "password": admin_new_password},
                )
                assert obsolete_admin_login.status_code == 401
                admin_login = await client.post(
                    "/api/v1/admin/auth/login",
                    json={"username": admin_username, "password": admin_final_password},
                )
                assert admin_login.status_code == 200
                admin_token = admin_login.json()["access_token"]

                provisioned = await client.post(
                    "/api/v1/admin/tenants",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "tenant_name": "Integration Tenant",
                        "tenant_slug": tenant_slug,
                        "owner_display_name": "Tenant Owner",
                        "owner_email": email,
                    },
                )
                assert provisioned.status_code == 201, provisioned.text
                provisioned_member = await client.post(
                    f"/api/v1/admin/tenants/{provisioned.json()['tenant']['id']}/users",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "display_name": "Integration Member",
                        "email": member_email,
                        "role": "member",
                    },
                )
                assert provisioned_member.status_code == 201, provisioned_member.text
                assert provisioned_member.json()["user"]["must_change_password"] is True
                assert len(provisioned_member.json()["initial_password"]) >= 12
                initial_login = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": tenant_slug,
                        "email": email,
                        "password": provisioned.json()["initial_password"],
                    },
                )
                assert initial_login.status_code == 200, initial_login.text
                assert initial_login.json()["password_change_required"] is True
                blocked_before_change = await client.get(
                    "/api/v1/auth/me",
                    headers={
                        "Authorization": f"Bearer {initial_login.json()['access_token']}"
                    },
                )
                assert blocked_before_change.status_code == 401
                changed_password = await client.post(
                    "/api/v1/auth/change-initial-password",
                    headers={
                        "Authorization": f"Bearer {initial_login.json()['access_token']}"
                    },
                    json={"new_password": password},
                )
                assert changed_password.status_code == 204, changed_password.text
                stale_initial_token = await client.get(
                    "/api/v1/auth/me",
                    headers={
                        "Authorization": f"Bearer {initial_login.json()['access_token']}"
                    },
                )
                assert stale_initial_token.status_code == 401
                registration = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": tenant_slug,
                        "email": email,
                        "password": password,
                    },
                )
                assert registration.status_code == 200, registration.text
                auth = registration.json()
                assert auth["tenant"]["slug"] == tenant_slug
                assert auth["password_change_required"] is False
                assert "tenant:manage" in auth["permissions"]
                assert "lc_asr_refresh" in client.cookies
                first_refresh_token = client.cookies["lc_asr_refresh"]

                me = await client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert me.status_code == 200, me.text
                assert me.json()["user"]["email"] == email

                current_tenant = await client.get(
                    "/api/v1/tenants/current",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert current_tenant.status_code == 200, current_tenant.text

                models = await client.get(
                    "/api/v1/models",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert models.status_code == 200, models.text
                assert models.json()[0]["provider_type"] == "local"
                assert models.json()[0]["model_kind"] == "speech"
                assert models.json()[0]["is_default"] is True
                model_health = await client.post(
                    f"/api/v1/models/{models.json()[0]['id']}/test",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert model_health.status_code == 200, model_health.text
                assert model_health.json()["status"] in {
                    "available",
                    "unavailable",
                    "misconfigured",
                }

                remote_model = await client.post(
                    "/api/v1/models",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "name": "Remote ASR",
                        "model_kind": "speech",
                        "provider_type": "openai_compatible",
                        "base_url": "https://asr.example.com/v1/",
                        "model_name": "remote-asr",
                        "api_key": "integration-speech-secret",
                    },
                )
                assert remote_model.status_code == 201, remote_model.text
                assert remote_model.json()["provider_type"] == "openai_compatible"
                assert remote_model.json()["has_api_key"] is True
                assert "api_key" not in remote_model.json()
                text_model = await client.post(
                    "/api/v1/models",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "name": "DeepSeek Text",
                        "model_kind": "text",
                        "provider_type": "deepseek",
                        "base_url": "https://api.deepseek.com",
                        "model_name": "deepseek-v4-flash",
                        "api_key": "integration-text-secret",
                    },
                )
                assert text_model.status_code == 201, text_model.text
                disposable_model = await client.post(
                    "/api/v1/models",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "name": "Disposable ASR",
                        "model_kind": "speech",
                        "provider_type": "openai_compatible",
                        "base_url": "https://disposable.example.com/v1",
                        "model_name": "delete-me",
                        "api_key": "disposable-integration-secret",
                    },
                )
                assert disposable_model.status_code == 201, disposable_model.text
                deleted_model = await client.delete(
                    f"/api/v1/models/{disposable_model.json()['id']}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert deleted_model.status_code == 204, deleted_model.text
                default_model = await client.post(
                    f"/api/v1/models/{remote_model.json()['id']}/default",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert default_model.status_code == 200, default_model.text
                assert default_model.json()["is_default"] is True

                disposable_batch = await client.post(
                    "/api/v1/uploads/batches",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "name": "Cancelled upload",
                        "files": [{"relative_path": "cancel.wav", "size_bytes": 1}],
                    },
                )
                assert disposable_batch.status_code == 201, disposable_batch.text
                cancelled_batch = await client.post(
                    f"/api/v1/uploads/batches/{disposable_batch.json()['id']}/cancel",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert cancelled_batch.status_code == 200, cancelled_batch.text
                assert cancelled_batch.json()["status"] == "cancelled"

                oversized = await client.post(
                    "/api/v1/uploads/batches",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "name": "Too large",
                        "files": [
                            {"relative_path": "huge-a.wav", "size_bytes": 3 * 1024**3},
                            {"relative_path": "huge-b.wav", "size_bytes": 3 * 1024**3},
                        ],
                    },
                )
                assert oversized.status_code == 413

                boundary = await client.post(
                    "/api/v1/uploads/batches",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "name": "Five GiB boundary",
                        "files": [{"relative_path": "boundary.wav", "size_bytes": 5 * 1024**3}],
                    },
                )
                assert boundary.status_code == 201, boundary.text
                assert boundary.json()["files"][0]["expected_chunks"] == 640
                await client.post(
                    f"/api/v1/uploads/batches/{boundary.json()['id']}/cancel",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )

                audio = b"RIFF-resumable-upload-test"
                digest = hashlib.sha256(audio).hexdigest()
                batch = await client.post(
                    "/api/v1/uploads/batches",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "name": "Upload integration",
                        "files": [{
                            "relative_path": "folder/sample.wav",
                            "size_bytes": len(audio),
                            "sha256": digest,
                        }],
                    },
                )
                assert batch.status_code == 201, batch.text
                upload_file = batch.json()["files"][0]
                chunk = await client.put(
                    f"/api/v1/uploads/files/{upload_file['id']}/chunks/0",
                    content=audio,
                    headers={
                        "Authorization": f"Bearer {auth['access_token']}",
                        "X-Chunk-SHA256": digest,
                        "Content-Type": "application/octet-stream",
                    },
                )
                assert chunk.status_code == 204, chunk.text
                duplicate_chunk = await client.put(
                    f"/api/v1/uploads/files/{upload_file['id']}/chunks/0",
                    content=audio,
                    headers={
                        "Authorization": f"Bearer {auth['access_token']}",
                        "X-Chunk-SHA256": digest,
                        "Content-Type": "application/octet-stream",
                    },
                )
                assert duplicate_chunk.status_code == 204, duplicate_chunk.text
                completed = await client.post(
                    f"/api/v1/uploads/files/{upload_file['id']}/complete",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert completed.status_code == 200, completed.text
                assert completed.json()["status"] == "ready"

                deduplicated_batch = await client.post(
                    "/api/v1/uploads/batches",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "name": "Deduplicated upload",
                        "files": [{
                            "relative_path": "renamed-copy.wav",
                            "size_bytes": len(audio),
                            "sha256": digest,
                        }],
                    },
                )
                assert deduplicated_batch.status_code == 201, deduplicated_batch.text
                reused_file = deduplicated_batch.json()["files"][0]
                assert reused_file["deduplicated"] is True
                assert reused_file["id"] == upload_file["id"]
                assert deduplicated_batch.json()["received_bytes"] == len(audio)

                jobs = await client.post(
                    "/api/v1/jobs",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "provider_id": models.json()[0]["id"],
                        "text_provider_id": text_model.json()["id"],
                        "uploaded_file_ids": [upload_file["id"]],
                        "language": "Chinese",
                        "diarize": False,
                        "speaker_mode": "double",
                    },
                )
                assert jobs.status_code == 201, jobs.text
                assert jobs.json()[0]["source_path"] == "folder/sample.wav"
                assert jobs.json()[0]["status"] == "queued"
                assert jobs.json()[0]["speaker_mode"] == "double"
                assert jobs.json()[0]["visibility"] == "private"
                assert jobs.json()[0]["provider_deleted"] is False
                assert jobs.json()[0]["text_provider_deleted"] is False
                job_id = jobs.json()[0]["id"]
                database = app.state.database
                async with database.connection() as connection:
                    await connection.execute(
                        """
                        UPDATE transcription_jobs
                        SET status = 'processing', attempts = 1,
                            last_heartbeat_at = now() - interval '10 minutes'
                        WHERE id = %s
                        """,
                        (job_id,),
                    )
                blocked_delete = await client.delete(
                    f"/api/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert blocked_delete.status_code == 409
                assert await recover_stale_jobs(database) >= 1
                recovered = await client.get(
                    f"/api/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert recovered.status_code == 200, recovered.text
                assert recovered.json()["status"] == "queued"
                cancelled = await client.post(
                    f"/api/v1/jobs/{job_id}/cancel",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert cancelled.status_code == 200, cancelled.text
                assert cancelled.json()["status"] == "cancelled"

                async with database.connection() as connection:
                    await connection.execute(
                        """
                        UPDATE transcription_jobs
                        SET status = 'failed', attempts = 1, cancel_requested_at = NULL
                        WHERE id = %s
                        """,
                        (job_id,),
                    )
                retried = await client.post(
                    f"/api/v1/jobs/{job_id}/retry",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert retried.status_code == 200, retried.text
                assert retried.json()["status"] == "queued"

                async with database.connection() as connection:
                    transcript = await (
                        await connection.execute(
                            """
                            INSERT INTO transcripts (
                                tenant_id, job_id, uploaded_file_id, provider_id,
                                language, text, duration_seconds
                            ) VALUES (%s, %s, %s, %s, 'Chinese', '测试文本', 1.25)
                            RETURNING id
                            """,
                            (
                                auth["tenant"]["id"],
                                job_id,
                                upload_file["id"],
                                models.json()[0]["id"],
                            ),
                        )
                    ).fetchone()
                    assert transcript is not None
                    await connection.execute(
                        """
                        INSERT INTO transcript_segments (
                            transcript_id, segment_index, start_seconds,
                            end_seconds, speaker, text
                        ) VALUES (%s, 0, 0, 1.25, 'SPEAKER_00', '测试文本')
                        """,
                        (transcript["id"],),
                    )
                    await connection.execute(
                        """
                        UPDATE transcription_jobs
                        SET status = 'completed', progress_percent = 100, completed_at = now()
                        WHERE id = %s
                        """,
                        (job_id,),
                    )
                detail = await client.get(
                    f"/api/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert detail.status_code == 200, detail.text
                assert detail.json()["segments"][0]["speaker"] == "SPEAKER_00"
                history = await client.get(
                    "/api/v1/uploads/history",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert history.status_code == 200, history.text
                historical = next(item for item in history.json() if item["sha256"] == digest)
                assert historical["id"] == upload_file["id"]
                assert historical["job_count"] == 1
                reprocessed = await client.post(
                    "/api/v1/jobs",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "provider_id": remote_model.json()["id"],
                        "text_provider_id": text_model.json()["id"],
                        "uploaded_file_ids": [historical["id"]],
                        "language": "Chinese",
                        "diarize": False,
                    },
                )
                assert reprocessed.status_code == 201, reprocessed.text
                reprocessed_job_id = reprocessed.json()[0]["id"]
                await client.post(
                    f"/api/v1/jobs/{reprocessed_job_id}/cancel",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                deleted_reprocessed = await client.delete(
                    f"/api/v1/jobs/{reprocessed_job_id}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert deleted_reprocessed.status_code == 200, deleted_reprocessed.text
                assert deleted_reprocessed.json()["deleted_jobs"] == 1
                assert deleted_reprocessed.json()["source_deleted"] is False
                retained_history = await client.get(
                    "/api/v1/uploads/history",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                retained = next(
                    item for item in retained_history.json() if item["sha256"] == digest
                )
                assert retained["job_count"] == 1
                summary = await client.get(
                    "/api/v1/workspace/summary",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert summary.status_code == 200, summary.text
                assert summary.json()["completed_tasks"] == 1
                assert summary.json()["available_models"] == 3
                assert summary.json()["historical_files"] >= 1
                subtitle = await client.get(
                    f"/api/v1/jobs/{job_id}/export/srt",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert subtitle.status_code == 200, subtitle.text
                assert "00:00:00,000 --> 00:00:01,250" in subtitle.text
                html_export = await client.get(
                    f"/api/v1/jobs/{job_id}/export/html",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert html_export.status_code == 200, html_export.text
                assert "<!doctype html>" in html_export.text
                assert "conversation" in html_export.text
                admin_jobs = await client.get(
                    "/api/v1/admin/jobs",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert admin_jobs.status_code == 200, admin_jobs.text
                admin_job = next(item for item in admin_jobs.json() if item["id"] == job_id)
                assert admin_job["tenant_slug"] == tenant_slug
                assert admin_job["created_by_email"] == email
                admin_job_detail = await client.get(
                    f"/api/v1/admin/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert admin_job_detail.status_code == 200, admin_job_detail.text
                assert admin_job_detail.json()["transcript_text"] == "测试文本"
                assert admin_job_detail.json()["segments"][0]["text"] == "测试文本"
                admin_recordings = await client.get(
                    "/api/v1/admin/recordings",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert admin_recordings.status_code == 200, admin_recordings.text
                admin_recording = next(
                    item for item in admin_recordings.json() if item["id"] == upload_file["id"]
                )
                assert admin_recording["tenant_slug"] == tenant_slug
                assert admin_recording["job_count"] == 1
                admin_export = await client.get(
                    f"/api/v1/admin/jobs/{job_id}/export/html",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert admin_export.status_code == 200, admin_export.text
                assert "conversation" in admin_export.text
                admin_recording_models = await client.get(
                    f"/api/v1/admin/recordings/{upload_file['id']}/models",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert admin_recording_models.status_code == 200
                assert any(
                    model["model_kind"] == "speech"
                    for model in admin_recording_models.json()["models"]
                )
                assert any(
                    model["model_kind"] == "text"
                    for model in admin_recording_models.json()["models"]
                )
                admin_created_job = await client.post(
                    f"/api/v1/admin/recordings/{upload_file['id']}/jobs",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "provider_id": remote_model.json()["id"],
                        "text_provider_id": text_model.json()["id"],
                        "language": "Chinese",
                        "diarize": True,
                        "speaker_mode": "multiple",
                    },
                )
                assert admin_created_job.status_code == 201, admin_created_job.text
                assert admin_created_job.json()["tenant_slug"] == tenant_slug
                assert admin_created_job.json()["speaker_mode"] == "multiple"
                await client.post(
                    f"/api/v1/jobs/{admin_created_job.json()['id']}/cancel",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                deleted_admin_job = await client.delete(
                    f"/api/v1/jobs/{admin_created_job.json()['id']}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert deleted_admin_job.status_code == 200

                archive_buffer = io.BytesIO()
                with zipfile.ZipFile(archive_buffer, "w") as archive:
                    archive.writestr("folder/interview.wav", b"RIFF-archive-audio")
                archive_bytes = archive_buffer.getvalue()
                archive_digest = hashlib.sha256(archive_bytes).hexdigest()
                archive_batch = await client.post(
                    "/api/v1/uploads/batches",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "name": "Archive integration",
                        "files": [{
                            "relative_path": "interviews.zip",
                            "size_bytes": len(archive_bytes),
                            "archive_type": "zip",
                        }],
                    },
                )
                assert archive_batch.status_code == 201, archive_batch.text
                archive_file = archive_batch.json()["files"][0]
                archive_chunk = await client.put(
                    f"/api/v1/uploads/files/{archive_file['id']}/chunks/0",
                    content=archive_bytes,
                    headers={
                        "Authorization": f"Bearer {auth['access_token']}",
                        "X-Chunk-SHA256": archive_digest,
                        "Content-Type": "application/octet-stream",
                    },
                )
                assert archive_chunk.status_code == 204, archive_chunk.text
                archive_completed = await client.post(
                    f"/api/v1/uploads/files/{archive_file['id']}/complete",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert archive_completed.status_code == 200, archive_completed.text
                extracted_id = archive_completed.json()["ready_file_ids"][0]
                assert extracted_id != archive_file["id"]
                archive_root = (
                    app.state.settings.data_path
                    / "uploads"
                    / auth["tenant"]["id"]
                    / archive_file["id"]
                )
                assert archive_root.exists()
                archive_job = await client.post(
                    "/api/v1/jobs",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={
                        "provider_id": models.json()[0]["id"],
                        "text_provider_id": text_model.json()["id"],
                        "uploaded_file_ids": [extracted_id],
                        "language": "Chinese",
                        "diarize": False,
                    },
                )
                assert archive_job.status_code == 201, archive_job.text
                assert archive_job.json()[0]["source_path"] == (
                    "interviews.zip!/folder/interview.wav"
                )
                archive_job_id = archive_job.json()[0]["id"]
                await client.post(
                    f"/api/v1/jobs/{archive_job_id}/cancel",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                deleted_archive = await client.delete(
                    f"/api/v1/uploads/history/{extracted_id}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert deleted_archive.status_code == 200, deleted_archive.text
                assert deleted_archive.json()["deleted_jobs"] == 1
                assert deleted_archive.json()["deleted_files"] == 2
                assert not archive_root.exists()
                deleted_archive_job = await client.get(
                    f"/api/v1/jobs/{archive_job_id}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert deleted_archive_job.status_code == 404

                refreshed = await client.post("/api/v1/auth/refresh")
                assert refreshed.status_code == 200, refreshed.text
                assert refreshed.json()["access_token"] != auth["access_token"]
                assert client.cookies["lc_asr_refresh"] != first_refresh_token

                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                    cookies={"lc_asr_refresh": first_refresh_token},
                ) as replay_client:
                    replay = await replay_client.post("/api/v1/auth/refresh")
                    assert replay.status_code == 401

                database = app.state.database
                async with database.connection() as connection:
                    await connection.execute(
                        """
                        DELETE FROM role_permissions rp
                        USING membership_roles mr, memberships m, users u, tenants t, permissions p
                        WHERE rp.role_id = mr.role_id
                          AND mr.membership_id = m.id
                          AND m.user_id = u.id
                          AND m.tenant_id = t.id
                          AND rp.permission_id = p.id
                          AND u.normalized_email = %s
                          AND t.slug = %s
                          AND p.code = 'tenant:read'
                        """,
                        (email, tenant_slug),
                    )
                forbidden = await client.get(
                    "/api/v1/tenants/current",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert forbidden.status_code == 403

                removed_public_registration = await client.post(
                    "/api/v1/auth/register",
                    json={
                        "tenant_name": "Duplicate",
                        "tenant_slug": tenant_slug,
                        "display_name": "Duplicate Owner",
                        "email": f"duplicate-{suffix}@example.com",
                        "password": password,
                    },
                )
                assert removed_public_registration.status_code == 404

                duplicate = await client.post(
                    "/api/v1/admin/tenants",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "tenant_name": "Other Tenant",
                        "tenant_slug": tenant_slug,
                        "owner_display_name": "Duplicate Owner",
                        "owner_email": f"duplicate-{suffix}@example.com",
                    },
                )
                assert duplicate.status_code == 409

                second_provisioned = await client.post(
                    "/api/v1/admin/tenants",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={
                        "tenant_name": "Other Tenant",
                        "tenant_slug": second_tenant_slug,
                        "owner_display_name": "Other Owner",
                        "owner_email": second_email,
                    },
                )
                assert second_provisioned.status_code == 201, second_provisioned.text
                second_initial_login = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": second_tenant_slug,
                        "email": second_email,
                        "password": second_provisioned.json()["initial_password"],
                    },
                )
                assert second_initial_login.status_code == 200
                second_changed = await client.post(
                    "/api/v1/auth/change-initial-password",
                    headers={
                        "Authorization": (
                            f"Bearer {second_initial_login.json()['access_token']}"
                        )
                    },
                    json={"new_password": second_password},
                )
                assert second_changed.status_code == 204
                second_registration = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": second_tenant_slug,
                        "email": second_email,
                        "password": second_password,
                    },
                )
                assert second_registration.status_code == 200, second_registration.text
                second_token = second_registration.json()["access_token"]
                private_public_list = await client.get(
                    "/api/v1/jobs/public",
                    headers={"Authorization": f"Bearer {second_token}"},
                )
                assert private_public_list.status_code == 200
                assert all(item["id"] != job_id for item in private_public_list.json())
                private_public_detail = await client.get(
                    f"/api/v1/jobs/public/{job_id}",
                    headers={"Authorization": f"Bearer {second_token}"},
                )
                assert private_public_detail.status_code == 404
                published = await client.patch(
                    f"/api/v1/jobs/{job_id}/visibility",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                    json={"visibility": "public"},
                )
                assert published.status_code == 200, published.text
                assert published.json()["visibility"] == "public"
                public_detail = await client.get(
                    f"/api/v1/jobs/public/{job_id}",
                    headers={"Authorization": f"Bearer {second_token}"},
                )
                assert public_detail.status_code == 200, public_detail.text
                assert public_detail.json()["tenant_slug"] == tenant_slug
                assert public_detail.json()["transcript_text"] == "测试文本"
                public_export = await client.get(
                    f"/api/v1/jobs/public/{job_id}/export/srt",
                    headers={"Authorization": f"Bearer {second_token}"},
                )
                assert public_export.status_code == 200, public_export.text
                assert "00:00:00,000 --> 00:00:01,250" in public_export.text
                disabled_second_user = await client.patch(
                    f"/api/v1/admin/users/{second_provisioned.json()['user']['id']}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"status": "disabled"},
                )
                assert disabled_second_user.status_code == 200, disabled_second_user.text
                disabled_access = await client.get(
                    "/api/v1/auth/me",
                    headers={
                        "Authorization": (
                            f"Bearer {second_registration.json()['access_token']}"
                        )
                    },
                )
                assert disabled_access.status_code == 401
                enabled_second_user = await client.patch(
                    f"/api/v1/admin/users/{second_provisioned.json()['user']['id']}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"status": "active"},
                )
                assert enabled_second_user.status_code == 200

                suspended_second_tenant = await client.patch(
                    f"/api/v1/admin/tenants/{second_provisioned.json()['tenant']['id']}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"status": "suspended"},
                )
                assert suspended_second_tenant.status_code == 200
                assert suspended_second_tenant.json()["status"] == "suspended"
                suspended_access = await client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {second_token}"},
                )
                assert suspended_access.status_code == 401
                resumed_second_tenant = await client.patch(
                    f"/api/v1/admin/tenants/{second_provisioned.json()['tenant']['id']}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    json={"status": "active"},
                )
                assert resumed_second_tenant.status_code == 200
                second_registration = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": second_tenant_slug,
                        "email": second_email,
                        "password": second_password,
                    },
                )
                assert second_registration.status_code == 200
                second_token = second_registration.json()["access_token"]
                wrong_current_password = await client.post(
                    "/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {second_token}"},
                    json={
                        "current_password": "wrong-password",
                        "new_password": second_updated_password,
                    },
                )
                assert wrong_current_password.status_code == 400
                weak_replacement = await client.post(
                    "/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {second_token}"},
                    json={
                        "current_password": second_password,
                        "new_password": "abcdefgh",
                    },
                )
                assert weak_replacement.status_code == 422
                changed_current_password = await client.post(
                    "/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {second_token}"},
                    json={
                        "current_password": second_password,
                        "new_password": second_updated_password,
                    },
                )
                assert changed_current_password.status_code == 204
                old_password_login = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": second_tenant_slug,
                        "email": second_email,
                        "password": second_password,
                    },
                )
                assert old_password_login.status_code == 401
                second_registration = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": second_tenant_slug,
                        "email": second_email,
                        "password": second_updated_password,
                    },
                )
                assert second_registration.status_code == 200
                second_token = second_registration.json()["access_token"]
                reset_second_password = await client.post(
                    f"/api/v1/admin/users/{second_provisioned.json()['user']['id']}/reset-password",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert reset_second_password.status_code == 200
                assert len(reset_second_password.json()["initial_password"]) >= 8
                reset_blocked_access = await client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {second_token}"},
                )
                assert reset_blocked_access.status_code == 403
                reset_initial_login = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": second_tenant_slug,
                        "email": second_email,
                        "password": reset_second_password.json()["initial_password"],
                    },
                )
                assert reset_initial_login.status_code == 200
                assert reset_initial_login.json()["password_change_required"] is True
                reset_changed = await client.post(
                    "/api/v1/auth/change-initial-password",
                    headers={
                        "Authorization": (
                            f"Bearer {reset_initial_login.json()['access_token']}"
                        )
                    },
                    json={"new_password": second_reset_password},
                )
                assert reset_changed.status_code == 204
                second_registration = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": second_tenant_slug,
                        "email": second_email,
                        "password": second_reset_password,
                    },
                )
                assert second_registration.status_code == 200
                second_token = second_registration.json()["access_token"]

                cross_tenant_upload = await client.get(
                    f"/api/v1/uploads/files/{upload_file['id']}",
                    headers={
                        "Authorization": (
                            f"Bearer {second_registration.json()['access_token']}"
                        )
                    },
                )
                assert cross_tenant_upload.status_code == 404

                cross_tenant_delete = await client.delete(
                    f"/api/v1/jobs/{job_id}",
                    headers={
                        "Authorization": (
                            f"Bearer {second_registration.json()['access_token']}"
                        )
                    },
                )
                assert cross_tenant_delete.status_code == 404

                cross_tenant_login = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": second_tenant_slug,
                        "email": email,
                        "password": password,
                    },
                )
                assert cross_tenant_login.status_code == 401

                deleted_speech_model = await client.delete(
                    f"/api/v1/models/{models.json()[0]['id']}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert deleted_speech_model.status_code == 204
                deleted_text_model = await client.delete(
                    f"/api/v1/models/{text_model.json()['id']}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert deleted_text_model.status_code == 204
                historical_after_model_deletion = await client.get(
                    f"/api/v1/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert historical_after_model_deletion.status_code == 200
                assert historical_after_model_deletion.json()["provider_name"] == (
                    models.json()[0]["name"]
                )
                assert historical_after_model_deletion.json()["text_provider_name"] == (
                    text_model.json()["name"]
                )
                assert historical_after_model_deletion.json()["provider_deleted"] is True
                assert (
                    historical_after_model_deletion.json()["text_provider_deleted"] is True
                )
                active_models_after_deletion = await client.get(
                    "/api/v1/models",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                active_model_ids = {item["id"] for item in active_models_after_deletion.json()}
                assert models.json()[0]["id"] not in active_model_ids
                assert text_model.json()["id"] not in active_model_ids
                export_after_model_deletion = await client.get(
                    f"/api/v1/jobs/{job_id}/export/html",
                    headers={"Authorization": f"Bearer {auth['access_token']}"},
                )
                assert export_after_model_deletion.status_code == 200

                async with database.connection() as connection:
                    preserved = await (
                        await connection.execute(
                            "SELECT storage_path FROM uploaded_files WHERE id = %s",
                            (upload_file["id"],),
                        )
                    ).fetchone()
                assert preserved is not None
                preserved_path = app.state.settings.data_path / preserved["storage_path"]
                assert preserved_path.exists()
                deleted_tenant = await client.delete(
                    f"/api/v1/admin/tenants/{provisioned.json()['tenant']['id']}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                assert deleted_tenant.status_code == 200, deleted_tenant.text
                assert deleted_tenant.json()["deleted_jobs"] == 1
                assert deleted_tenant.json()["retained_recordings"] >= 1
                assert preserved_path.exists()
                deleted_tenant_recordings = await client.get(
                    "/api/v1/admin/recordings",
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                retained_recording = next(
                    item
                    for item in deleted_tenant_recordings.json()
                    if item["id"] == upload_file["id"]
                )
                assert retained_recording["tenant_status"] == "deleted"
                assert retained_recording["job_count"] == 0
                removed_public_job = await client.get(
                    f"/api/v1/jobs/public/{job_id}",
                    headers={"Authorization": f"Bearer {second_token}"},
                )
                assert removed_public_job.status_code == 404
                deleted_tenant_login = await client.post(
                    "/api/v1/auth/login",
                    json={
                        "tenant_slug": tenant_slug,
                        "email": email,
                        "password": password,
                    },
                )
                assert deleted_tenant_login.status_code == 401

                logout = await client.post("/api/v1/auth/logout")
                assert logout.status_code == 200
            finally:
                database = app.state.database
                async with database.connection() as connection:
                    await connection.execute(
                        "DELETE FROM tenants WHERE slug IN (%s, %s)",
                        (tenant_slug, second_tenant_slug),
                    )
                    await connection.execute(
                        "DELETE FROM users WHERE normalized_email IN (%s, %s, %s, %s)",
                        (
                            email,
                            member_email,
                            second_email,
                            f"duplicate-{suffix}@example.com",
                        ),
                    )
                    await connection.execute(
                        "DELETE FROM platform_admins WHERE username = %s",
                        (admin_username,),
                    )
                if "auth" in locals():
                    tenant_uploads = app.state.settings.data_path / "uploads" / auth["tenant"]["id"]
                    shutil.rmtree(tenant_uploads, ignore_errors=True)
