"""Cross-tenant persistence available only to platform administrators."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from psycopg import AsyncConnection


@dataclass(frozen=True, slots=True)
class PlatformAdmin:
    id: UUID
    username: str
    password_hash: str
    must_change_password: bool
    locked_until: datetime | None


class AdminRepository:
    async def find_by_username(
        self,
        connection: AsyncConnection[dict[str, object]],
        username: str,
    ) -> PlatformAdmin | None:
        row = await (
            await connection.execute(
                """
                SELECT id, username, password_hash, must_change_password, locked_until
                FROM platform_admins
                WHERE username = %s AND status = 'active'
                """,
                (username,),
            )
        ).fetchone()
        return None if row is None else PlatformAdmin(**row)  # type: ignore[arg-type]

    async def find_active_by_id(
        self,
        connection: AsyncConnection[dict[str, object]],
        admin_id: UUID,
    ) -> PlatformAdmin | None:
        row = await (
            await connection.execute(
                """
                SELECT id, username, password_hash, must_change_password, locked_until
                FROM platform_admins
                WHERE id = %s AND status = 'active'
                """,
                (admin_id,),
            )
        ).fetchone()
        return None if row is None else PlatformAdmin(**row)  # type: ignore[arg-type]

    async def consume_login_limit(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        scope: str,
        key_hash: str,
        max_attempts: int,
        window_seconds: int,
        block_seconds: int,
    ) -> int | None:
        await connection.execute(
            """
            INSERT INTO platform_admin_login_limits (scope, key_hash, attempts)
            VALUES (%s, %s, 0)
            ON CONFLICT (scope, key_hash) DO NOTHING
            """,
            (scope, key_hash),
        )
        row = await (
            await connection.execute(
                """
                SELECT window_started_at, attempts, blocked_until, now() AS database_now
                FROM platform_admin_login_limits
                WHERE scope = %s AND key_hash = %s
                FOR UPDATE
                """,
                (scope, key_hash),
            )
        ).fetchone()
        assert row is not None
        now = cast(datetime, row["database_now"])
        blocked_until = cast(datetime | None, row["blocked_until"])
        if blocked_until is not None and blocked_until > now:
            return max(1, int((blocked_until - now).total_seconds()))
        window_expired = (
            now - cast(datetime, row["window_started_at"])
        ).total_seconds() >= window_seconds
        attempts = 1 if window_expired else cast(int, row["attempts"]) + 1
        if attempts > max_attempts:
            updated = await (
                await connection.execute(
                    """
                    UPDATE platform_admin_login_limits
                    SET attempts = %s,
                        window_started_at = CASE WHEN %s THEN now()
                                                 ELSE window_started_at END,
                        blocked_until = now() + make_interval(secs => %s),
                        updated_at = now()
                    WHERE scope = %s AND key_hash = %s
                    RETURNING blocked_until, now() AS database_now
                    """,
                    (attempts, window_expired, block_seconds, scope, key_hash),
                )
            ).fetchone()
            assert updated is not None
            updated_until = cast(datetime, updated["blocked_until"])
            updated_now = cast(datetime, updated["database_now"])
            return max(
                1,
                int((updated_until - updated_now).total_seconds()),
            )
        await connection.execute(
            """
            UPDATE platform_admin_login_limits
            SET attempts = %s,
                window_started_at = CASE WHEN %s THEN now() ELSE window_started_at END,
                blocked_until = NULL,
                updated_at = now()
            WHERE scope = %s AND key_hash = %s
            """,
            (attempts, window_expired, scope, key_hash),
        )
        return None

    async def record_failed_login(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        admin_id: UUID,
        max_failures: int,
        window_seconds: int,
        lock_seconds: int,
    ) -> int | None:
        row = await (
            await connection.execute(
                """
                SELECT failed_login_attempts, failed_login_window_started_at,
                       locked_until, now() AS database_now
                FROM platform_admins
                WHERE id = %s AND status = 'active'
                FOR UPDATE
                """,
                (admin_id,),
            )
        ).fetchone()
        if row is None:
            return None
        now = cast(datetime, row["database_now"])
        locked_until = cast(datetime | None, row["locked_until"])
        if locked_until is not None and locked_until > now:
            return max(1, int((locked_until - now).total_seconds()))
        window_started = cast(datetime | None, row["failed_login_window_started_at"])
        window_expired = (
            window_started is None or (now - window_started).total_seconds() >= window_seconds
        )
        attempts = 1 if window_expired else cast(int, row["failed_login_attempts"]) + 1
        locked = attempts >= max_failures
        updated = await (
            await connection.execute(
                """
                UPDATE platform_admins
                SET failed_login_attempts = %s,
                    failed_login_window_started_at =
                        CASE WHEN %s THEN now() ELSE failed_login_window_started_at END,
                    last_failed_login_at = now(),
                    locked_until =
                        CASE WHEN %s THEN now() + make_interval(secs => %s) ELSE NULL END,
                    updated_at = now()
                WHERE id = %s
                RETURNING locked_until, now() AS database_now
                """,
                (attempts, window_expired, locked, lock_seconds, admin_id),
            )
        ).fetchone()
        assert updated is not None
        updated_until = cast(datetime | None, updated["locked_until"])
        if updated_until is None:
            return None
        updated_now = cast(datetime, updated["database_now"])
        return max(
            1,
            int((updated_until - updated_now).total_seconds()),
        )

    async def clear_login_limit(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        scope: str,
        key_hash: str,
    ) -> None:
        await connection.execute(
            """
            DELETE FROM platform_admin_login_limits
            WHERE scope = %s AND key_hash = %s
            """,
            (scope, key_hash),
        )

    async def record_successful_login(
        self,
        connection: AsyncConnection[dict[str, object]],
        admin_id: UUID,
    ) -> int | None:
        row = await (
            await connection.execute(
                """
                SELECT locked_until, now() AS database_now
                FROM platform_admins
                WHERE id = %s AND status = 'active'
                FOR UPDATE
                """,
                (admin_id,),
            )
        ).fetchone()
        if row is None:
            return 1
        locked_until = cast(datetime | None, row["locked_until"])
        database_now = cast(datetime, row["database_now"])
        if locked_until is not None and locked_until > database_now:
            return max(
                1,
                int((locked_until - database_now).total_seconds()),
            )
        await connection.execute(
            """
            UPDATE platform_admins
            SET last_login_at = now(), failed_login_attempts = 0,
                failed_login_window_started_at = NULL, locked_until = NULL,
                updated_at = now()
            WHERE id = %s
            """,
            (admin_id,),
        )
        return None

    async def change_password(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        admin_id: UUID,
        password_hash: str,
    ) -> bool:
        result = await connection.execute(
            """
            UPDATE platform_admins
            SET password_hash = %s, must_change_password = false, updated_at = now()
            WHERE id = %s AND status = 'active' AND must_change_password
            """,
            (password_hash, admin_id),
        )
        return result.rowcount == 1

    async def replace_current_password(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        admin_id: UUID,
        password_hash: str,
    ) -> bool:
        result = await connection.execute(
            """
            UPDATE platform_admins
            SET password_hash = %s, updated_at = now()
            WHERE id = %s AND status = 'active' AND NOT must_change_password
            """,
            (password_hash, admin_id),
        )
        return result.rowcount == 1

    async def list_tenants(
        self,
        connection: AsyncConnection[dict[str, object]],
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT id, slug, name, status, created_at
            FROM tenants
            WHERE status <> 'deleted'
            ORDER BY created_at DESC
            """
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def list_users(
        self,
        connection: AsyncConnection[dict[str, object]],
        tenant_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT u.id, t.id AS tenant_id, t.name AS tenant_name, t.slug AS tenant_slug,
                   u.email, u.display_name, u.status, m.status AS membership_status,
                   u.must_change_password, u.created_at
            FROM users u
            JOIN memberships m ON m.user_id = u.id
            JOIN tenants t ON t.id = m.tenant_id
            WHERE (%s::uuid IS NULL OR t.id = %s)
            ORDER BY t.name, u.created_at
            """,
            (tenant_id, tenant_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def add_tenant_user(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        email: str,
        display_name: str,
        password_hash: str,
        role: str,
    ) -> dict[str, Any] | None:
        tenant = await (
            await connection.execute(
                "SELECT id, name, slug FROM tenants WHERE id = %s AND status = 'active'",
                (tenant_id,),
            )
        ).fetchone()
        if tenant is None:
            return None
        user = await (
            await connection.execute(
                """
                INSERT INTO users (
                    email, normalized_email, display_name, password_hash,
                    must_change_password
                ) VALUES (%s, %s, %s, %s, true)
                RETURNING id, email, display_name, status, must_change_password, created_at
                """,
                (email, email, display_name, password_hash),
            )
        ).fetchone()
        assert user is not None
        membership = await (
            await connection.execute(
                """
                INSERT INTO memberships (tenant_id, user_id)
                VALUES (%s, %s)
                RETURNING id, status
                """,
                (tenant_id, user["id"]),
            )
        ).fetchone()
        assert membership is not None
        role_row = await (
            await connection.execute(
                "SELECT id FROM roles WHERE tenant_id = %s AND code = %s",
                (tenant_id, role),
            )
        ).fetchone()
        assert role_row is not None
        await connection.execute(
            """
            INSERT INTO membership_roles (tenant_id, membership_id, role_id)
            VALUES (%s, %s, %s)
            """,
            (tenant_id, membership["id"], role_row["id"]),
        )
        return {
            **dict(user),
            "tenant_id": tenant["id"],
            "tenant_name": tenant["name"],
            "tenant_slug": tenant["slug"],
            "membership_status": membership["status"],
        }

    async def update_user_status(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        user_id: UUID,
        user_status: str,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                """
                UPDATE users SET status = %s, updated_at = now()
                WHERE id = %s
                RETURNING id
                """,
                (user_status, user_id),
            )
        ).fetchone()
        if row is None:
            return None
        if user_status == "disabled":
            await connection.execute(
                """
                UPDATE refresh_sessions
                SET revoked_at = COALESCE(revoked_at, now())
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (user_id,),
            )
        users = await self.list_users(connection)
        return next((user for user in users if user["id"] == user_id), None)

    async def reset_user_password(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        user_id: UUID,
        password_hash: str,
    ) -> dict[str, Any] | None:
        updated = await connection.execute(
            """
            UPDATE users
            SET password_hash = %s, must_change_password = true, updated_at = now()
            WHERE id = %s
              AND EXISTS (
                  SELECT 1
                  FROM memberships m
                  JOIN tenants t ON t.id = m.tenant_id
                  WHERE m.user_id = users.id AND t.status <> 'deleted'
              )
            """,
            (password_hash, user_id),
        )
        if updated.rowcount != 1:
            return None
        await connection.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = COALESCE(revoked_at, now())
            WHERE user_id = %s AND revoked_at IS NULL
            """,
            (user_id,),
        )
        users = await self.list_users(connection)
        return next((user for user in users if user["id"] == user_id), None)

    async def update_tenant_status(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        tenant_status: str,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                """
                UPDATE tenants
                SET status = %s, updated_at = now()
                WHERE id = %s AND status <> 'deleted'
                RETURNING id, slug, name, status, created_at
                """,
                (tenant_status, tenant_id),
            )
        ).fetchone()
        if row is None:
            return None
        if tenant_status == "suspended":
            await connection.execute(
                """
                UPDATE refresh_sessions
                SET revoked_at = COALESCE(revoked_at, now())
                WHERE tenant_id = %s AND revoked_at IS NULL
                """,
                (tenant_id,),
            )
        return dict(row)

    async def business_delete_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
    ) -> dict[str, int] | None:
        tenant = await (
            await connection.execute(
                """
                SELECT id FROM tenants
                WHERE id = %s AND status <> 'deleted'
                FOR UPDATE
                """,
                (tenant_id,),
            )
        ).fetchone()
        if tenant is None:
            return None
        processing = await (
            await connection.execute(
                """
                SELECT count(*) AS count
                FROM transcription_jobs
                WHERE tenant_id = %s AND status IN ('processing', 'refining')
                """,
                (tenant_id,),
            )
        ).fetchone()
        assert processing is not None
        if int(str(processing["count"])) > 0:
            return {"blocked": 1, "deleted_jobs": 0, "retained_recordings": 0}
        recordings = await (
            await connection.execute(
                """
                SELECT count(*) AS count
                FROM uploaded_files
                WHERE tenant_id = %s AND status = 'ready' AND archive_type IS NULL
                """,
                (tenant_id,),
            )
        ).fetchone()
        jobs = await (
            await connection.execute(
                "SELECT count(*) AS count FROM transcription_jobs WHERE tenant_id = %s",
                (tenant_id,),
            )
        ).fetchone()
        assert recordings is not None and jobs is not None
        await connection.execute(
            """
            UPDATE tenants
            SET status = 'deleted', deleted_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (tenant_id,),
        )
        await connection.execute(
            """
            UPDATE users
            SET status = 'disabled', updated_at = now()
            WHERE id IN (SELECT user_id FROM memberships WHERE tenant_id = %s)
            """,
            (tenant_id,),
        )
        await connection.execute(
            """
            UPDATE memberships
            SET status = 'suspended', updated_at = now()
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        await connection.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = COALESCE(revoked_at, now())
            WHERE tenant_id = %s AND revoked_at IS NULL
            """,
            (tenant_id,),
        )
        await connection.execute(
            "DELETE FROM transcription_jobs WHERE tenant_id = %s",
            (tenant_id,),
        )
        return {
            "blocked": 0,
            "deleted_jobs": int(str(jobs["count"])),
            "retained_recordings": int(str(recordings["count"])),
        }

    async def list_recordings(
        self,
        connection: AsyncConnection[dict[str, object]],
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT f.id, f.tenant_id, tn.slug AS tenant_slug, tn.name AS tenant_name,
                   tn.status AS tenant_status, f.original_name, f.relative_path,
                   f.media_type, f.size_bytes, f.sha256, f.created_at,
                   count(j.id)::integer AS job_count
            FROM uploaded_files f
            JOIN tenants tn ON tn.id = f.tenant_id
            LEFT JOIN transcription_jobs j ON j.uploaded_file_id = f.id
            WHERE f.status = 'ready' AND f.archive_type IS NULL
              AND f.file_kind = 'audio'
            GROUP BY f.id, tn.id
            ORDER BY f.created_at DESC
            """
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_recording(
        self,
        connection: AsyncConnection[dict[str, object]],
        recording_id: UUID,
    ) -> dict[str, Any] | None:
        rows = await self.list_recordings(connection)
        return next((item for item in rows if item["id"] == recording_id), None)

    async def list_recording_models(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        recording_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT p.id, p.name, p.provider_type, p.model_kind, p.base_url,
                   p.model_name, p.capabilities, p.is_enabled, p.is_default,
                   p.is_system, p.created_at,
                   (p.api_key_ciphertext IS NOT NULL OR p.api_key_env IS NOT NULL)
                       AS has_api_key
            FROM uploaded_files f
            JOIN tenants t ON t.id = f.tenant_id
            JOIN model_providers p ON p.tenant_id = f.tenant_id
            WHERE f.id = %s AND f.status = 'ready' AND f.archive_type IS NULL
              AND f.file_kind = 'audio'
              AND p.is_enabled
              AND p.deleted_at IS NULL
              AND (
                  p.model_kind = 'speech'
                  OR (p.model_kind = 'text' AND p.api_key_ciphertext IS NOT NULL)
              )
            ORDER BY p.model_kind, p.is_default DESC, p.name
            """,
            (recording_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def recording_job_context(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        recording_id: UUID,
    ) -> tuple[UUID, UUID] | None:
        row = await (
            await connection.execute(
                """
                SELECT f.tenant_id, u.id AS user_id
                FROM uploaded_files f
                JOIN tenants t ON t.id = f.tenant_id
                JOIN memberships m ON m.tenant_id = t.id
                JOIN users u ON u.id = m.user_id
                LEFT JOIN membership_roles mr ON mr.membership_id = m.id
                LEFT JOIN roles r ON r.id = mr.role_id
                WHERE f.id = %s AND f.status = 'ready' AND f.archive_type IS NULL
                  AND f.file_kind = 'audio'
                ORDER BY
                    CASE r.code WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,
                    u.created_at
                LIMIT 1
                FOR UPDATE OF f
                """,
                (recording_id,),
            )
        ).fetchone()
        if row is None:
            return None
        return row["tenant_id"], row["user_id"]  # type: ignore[return-value]

    async def list_jobs(
        self,
        connection: AsyncConnection[dict[str, object]],
        tenant_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            self._job_query(
                """
                WHERE (%s::uuid IS NULL OR j.tenant_id = %s)
                ORDER BY j.queued_at DESC
                """
            ),
            (tenant_id, tenant_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_job(
        self,
        connection: AsyncConnection[dict[str, object]],
        job_id: UUID,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                self._job_query("WHERE j.id = %s"),
                (job_id,),
            )
        ).fetchone()
        return None if row is None else dict(row)

    async def update_job_visibility(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        job_id: UUID,
        visibility: str,
    ) -> dict[str, Any] | None:
        changed = await connection.execute(
            """
            UPDATE transcription_jobs
            SET visibility = %s, updated_at = now()
            WHERE id = %s
            """,
            (visibility, job_id),
        )
        if changed.rowcount != 1:
            return None
        return await self.get_job(connection, job_id)

    async def job_segments(
        self,
        connection: AsyncConnection[dict[str, object]],
        job_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT s.segment_index, s.start_seconds, s.end_seconds, s.speaker, s.text
            FROM transcript_segments s
            JOIN transcripts t ON t.id = s.transcript_id
            WHERE t.job_id = %s
            ORDER BY s.segment_index
            """,
            (job_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    @staticmethod
    def _job_query(where_clause: str) -> str:
        return f"""
            SELECT j.id, j.tenant_id, tn.slug AS tenant_slug, tn.name AS tenant_name,
                   creator.email AS created_by_email,
                   creator.display_name AS created_by_name,
                   j.uploaded_file_id, j.provider_id, j.text_provider_id,
                   p.name AS provider_name, tp.name AS text_provider_name,
                   (p.deleted_at IS NOT NULL) AS provider_deleted,
                   (tp.deleted_at IS NOT NULL) AS text_provider_deleted,
                   j.provider_type_snapshot AS provider_type,
                   j.model_name_snapshot AS model_name,
                   j.text_model_name_snapshot AS text_model_name,
                   f.relative_path AS source_path, j.status, j.visibility,
                   j.language, j.diarize,
                   j.speaker_mode, j.progress_percent, j.attempts,
                   j.refinement_attempts, j.max_attempts, j.asr_completed_at,
                   (j.asr_result_checkpoint IS NOT NULL) AS has_asr_checkpoint,
                   j.cancel_requested_at, j.error_message, j.queued_at,
                   j.started_at, j.completed_at, t.id AS transcript_id,
                   t.text AS transcript_text
            FROM transcription_jobs j
            JOIN tenants tn ON tn.id = j.tenant_id
            JOIN users creator ON creator.id = j.created_by
            JOIN uploaded_files f ON f.id = j.uploaded_file_id
            JOIN model_providers p ON p.id = j.provider_id
            LEFT JOIN model_providers tp ON tp.id = j.text_provider_id
            LEFT JOIN transcripts t ON t.job_id = j.id
            {where_clause}
        """
