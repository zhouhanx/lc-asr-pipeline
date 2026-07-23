"""Tenant identity and RBAC persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from psycopg import AsyncConnection


@dataclass(frozen=True, slots=True)
class Account:
    user_id: UUID
    membership_id: UUID
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
    email: str
    display_name: str
    email_verified: bool
    must_change_password: bool
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class LoginAccount:
    account: Account
    password_hash: str


@dataclass(frozen=True, slots=True)
class RefreshSession:
    id: UUID
    account: Account
    expires_at: datetime
    revoked_at: datetime | None


class IdentityRepository:
    """Run tenant-scoped identity queries on a caller-managed transaction."""

    async def register_tenant_owner(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_slug: str,
        tenant_name: str,
        email: str,
        display_name: str,
        password_hash: str,
        must_change_password: bool = False,
    ) -> Account:
        tenant = await (
            await connection.execute(
                """
                INSERT INTO tenants (slug, name)
                VALUES (%s, %s)
                RETURNING id, slug, name
                """,
                (tenant_slug, tenant_name),
            )
        ).fetchone()
        assert tenant is not None

        await connection.execute(
            """
            INSERT INTO model_providers (
                tenant_id, name, provider_type, base_url, model_name,
                api_key_env, capabilities, is_default, model_kind, is_system
            )
            VALUES (
                %s, '本地 Qwen3-ASR 1.7B', 'local', 'http://127.0.0.1:8765',
                'qwen3-asr-1.7b-mlx-8bit', 'MLX_ASR_API_KEY',
                '["transcription", "timestamps", "diarization"]'::jsonb,
                true, 'speech', true
            )
            """,
            (tenant["id"],),
        )
        await connection.execute(
            """
            INSERT INTO model_providers (
                tenant_id, name, provider_type, base_url, model_name,
                api_key_env, capabilities, is_default, model_kind, is_system
            )
            VALUES (
                %s, 'PaddleOCR 文档识别', 'paddleocr',
                'https://paddleocr.aistudio-app.com/api/v2/ocr',
                'PaddleOCR-VL-1.6', 'PADDLE_API',
                '["ocr", "document_parsing", "markdown", "image", "pdf"]'::jsonb,
                true, 'ocr', true
            )
            """,
            (tenant["id"],),
        )

        user = await (
            await connection.execute(
                """
            INSERT INTO users (
                email, normalized_email, display_name, password_hash, must_change_password
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, email, display_name, email_verified_at, must_change_password
            """,
                (email, email, display_name, password_hash, must_change_password),
            )
        ).fetchone()
        assert user is not None

        membership = await (
            await connection.execute(
                """
                INSERT INTO memberships (tenant_id, user_id)
                VALUES (%s, %s)
                RETURNING id
                """,
                (tenant["id"], user["id"]),
            )
        ).fetchone()
        assert membership is not None

        roles: dict[str, UUID] = {}
        for code, name in (
            ("owner", "Owner"),
            ("admin", "Administrator"),
            ("member", "Member"),
        ):
            role = await (
                await connection.execute(
                    """
                    INSERT INTO roles (tenant_id, code, name, is_system)
                    VALUES (%s, %s, %s, true)
                    RETURNING id
                    """,
                    (tenant["id"], code, name),
                )
            ).fetchone()
            assert role is not None
            roles[code] = role["id"]  # type: ignore[assignment]

        await connection.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT %s, id FROM permissions
            """,
            (roles["owner"],),
        )
        await connection.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT %s, id FROM permissions
            WHERE code NOT IN ('tenant:manage', 'roles:manage')
            """,
            (roles["admin"],),
        )
        await connection.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT %s, id FROM permissions
            WHERE code IN (
                'workspace:read', 'jobs:read', 'models:read', 'agents:read',
                'members:read', 'roles:read', 'tenant:read'
            )
            """,
            (roles["member"],),
        )
        await connection.execute(
            "INSERT INTO membership_roles (membership_id, role_id) VALUES (%s, %s)",
            (membership["id"], roles["owner"]),
        )
        await connection.execute(
            """
            INSERT INTO audit_events (tenant_id, actor_user_id, event_type, target_type, target_id)
            VALUES (%s, %s, 'tenant.registered', 'tenant', %s)
            """,
            (tenant["id"], user["id"], str(tenant["id"])),
        )

        permissions = await self._permissions(connection, membership["id"])  # type: ignore[arg-type]
        return Account(
            user_id=user["id"],  # type: ignore[arg-type]
            membership_id=membership["id"],  # type: ignore[arg-type]
            tenant_id=tenant["id"],  # type: ignore[arg-type]
            tenant_slug=str(tenant["slug"]),
            tenant_name=str(tenant["name"]),
            email=str(user["email"]),
            display_name=str(user["display_name"]),
            email_verified=user["email_verified_at"] is not None,
            must_change_password=bool(user["must_change_password"]),
            permissions=frozenset(permissions),
        )

    async def find_login_account(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_slug: str,
        normalized_email: str,
    ) -> LoginAccount | None:
        row = await (
            await connection.execute(
                """
                SELECT
                    u.id AS user_id,
                    u.email,
                    u.display_name,
                    u.password_hash,
                    u.email_verified_at,
                    u.must_change_password,
                    m.id AS membership_id,
                    t.id AS tenant_id,
                    t.slug AS tenant_slug,
                    t.name AS tenant_name
                FROM tenants t
                JOIN memberships m ON m.tenant_id = t.id
                JOIN users u ON u.id = m.user_id
                WHERE t.slug = %s
                  AND u.normalized_email = %s
                  AND t.status = 'active'
                  AND u.status = 'active'
                  AND m.status = 'active'
                """,
                (tenant_slug, normalized_email),
            )
        ).fetchone()
        if row is None:
            return None
        account = await self._account_from_row(connection, row)
        return LoginAccount(account=account, password_hash=str(row["password_hash"]))

    async def find_active_account(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        user_id: UUID,
        tenant_id: UUID,
        membership_id: UUID,
    ) -> Account | None:
        row = await (
            await connection.execute(
                """
                SELECT
                    u.id AS user_id,
                    u.email,
                    u.display_name,
                    u.email_verified_at,
                    u.must_change_password,
                    m.id AS membership_id,
                    t.id AS tenant_id,
                    t.slug AS tenant_slug,
                    t.name AS tenant_name
                FROM memberships m
                JOIN users u ON u.id = m.user_id
                JOIN tenants t ON t.id = m.tenant_id
                WHERE u.id = %s AND t.id = %s AND m.id = %s
                  AND t.status = 'active'
                  AND u.status = 'active'
                  AND m.status = 'active'
                """,
                (user_id, tenant_id, membership_id),
            )
        ).fetchone()
        return None if row is None else await self._account_from_row(connection, row)

    async def create_refresh_session(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        account: Account,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_address: str | None,
    ) -> UUID:
        row = await (
            await connection.execute(
                """
                INSERT INTO refresh_sessions (
                    tenant_id, user_id, membership_id, token_hash, expires_at,
                    user_agent, ip_address
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    account.tenant_id,
                    account.user_id,
                    account.membership_id,
                    token_hash,
                    expires_at,
                    user_agent,
                    ip_address,
                ),
            )
        ).fetchone()
        assert row is not None
        return row["id"]  # type: ignore[return-value]

    async def find_refresh_session_for_update(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        token_hash: str,
    ) -> RefreshSession | None:
        row = await (
            await connection.execute(
                """
                SELECT
                    rs.id AS session_id,
                    rs.expires_at,
                    rs.revoked_at,
                    u.id AS user_id,
                    u.email,
                    u.display_name,
                    u.email_verified_at,
                    u.must_change_password,
                    m.id AS membership_id,
                    t.id AS tenant_id,
                    t.slug AS tenant_slug,
                    t.name AS tenant_name
                FROM refresh_sessions rs
                JOIN memberships m ON m.id = rs.membership_id
                JOIN users u ON u.id = rs.user_id
                JOIN tenants t ON t.id = rs.tenant_id
                WHERE rs.token_hash = %s
                  AND t.status = 'active'
                  AND u.status = 'active'
                  AND m.status = 'active'
                FOR UPDATE OF rs
                """,
                (token_hash,),
            )
        ).fetchone()
        if row is None:
            return None
        account = await self._account_from_row(connection, row)
        return RefreshSession(
            id=row["session_id"],  # type: ignore[arg-type]
            account=account,
            expires_at=row["expires_at"],  # type: ignore[arg-type]
            revoked_at=row["revoked_at"],  # type: ignore[arg-type]
        )

    async def rotate_refresh_session(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        old_session_id: UUID,
        new_session_id: UUID,
    ) -> None:
        await connection.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = now(), replaced_by_id = %s
            WHERE id = %s AND revoked_at IS NULL
            """,
            (new_session_id, old_session_id),
        )

    async def revoke_refresh_session(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        token_hash: str,
    ) -> None:
        await connection.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = COALESCE(revoked_at, now())
            WHERE token_hash = %s
            """,
            (token_hash,),
        )

    async def change_password(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        account: Account,
        password_hash: str,
    ) -> bool:
        updated = await connection.execute(
            """
            UPDATE users
            SET password_hash = %s, must_change_password = false, updated_at = now()
            WHERE id = %s AND status = 'active' AND must_change_password
            """,
            (password_hash, account.user_id),
        )
        if updated.rowcount != 1:
            return False
        await connection.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = COALESCE(revoked_at, now())
            WHERE user_id = %s AND revoked_at IS NULL
            """,
            (account.user_id,),
        )
        await connection.execute(
            """
            INSERT INTO audit_events (
                tenant_id, actor_user_id, event_type, target_type, target_id
            ) VALUES (%s, %s, 'user.initial_password_changed', 'user', %s)
            """,
            (account.tenant_id, account.user_id, str(account.user_id)),
        )
        return True

    async def password_hash_for_account(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        account: Account,
    ) -> str | None:
        row = await (
            await connection.execute(
                """
                SELECT u.password_hash
                FROM users u
                JOIN memberships m ON m.user_id = u.id
                WHERE u.id = %s AND m.id = %s AND m.tenant_id = %s
                  AND u.status = 'active' AND m.status = 'active'
                FOR UPDATE OF u
                """,
                (account.user_id, account.membership_id, account.tenant_id),
            )
        ).fetchone()
        return None if row is None else str(row["password_hash"])

    async def replace_current_password(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        account: Account,
        password_hash: str,
    ) -> bool:
        updated = await connection.execute(
            """
            UPDATE users
            SET password_hash = %s, must_change_password = false, updated_at = now()
            WHERE id = %s AND status = 'active' AND NOT must_change_password
            """,
            (password_hash, account.user_id),
        )
        if updated.rowcount != 1:
            return False
        await connection.execute(
            """
            UPDATE refresh_sessions
            SET revoked_at = COALESCE(revoked_at, now())
            WHERE user_id = %s AND revoked_at IS NULL
            """,
            (account.user_id,),
        )
        await connection.execute(
            """
            INSERT INTO audit_events (
                tenant_id, actor_user_id, event_type, target_type, target_id
            ) VALUES (%s, %s, 'user.password_changed', 'user', %s)
            """,
            (account.tenant_id, account.user_id, str(account.user_id)),
        )
        return True

    async def _account_from_row(
        self,
        connection: AsyncConnection[dict[str, object]],
        row: dict[str, object],
    ) -> Account:
        membership_id = row["membership_id"]
        permissions = await self._permissions(connection, membership_id)  # type: ignore[arg-type]
        return Account(
            user_id=row["user_id"],  # type: ignore[arg-type]
            membership_id=membership_id,  # type: ignore[arg-type]
            tenant_id=row["tenant_id"],  # type: ignore[arg-type]
            tenant_slug=str(row["tenant_slug"]),
            tenant_name=str(row["tenant_name"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]),
            email_verified=row["email_verified_at"] is not None,
            must_change_password=bool(row["must_change_password"]),
            permissions=frozenset(permissions),
        )

    async def _permissions(
        self,
        connection: AsyncConnection[dict[str, object]],
        membership_id: UUID,
    ) -> set[str]:
        cursor = await connection.execute(
            """
            SELECT DISTINCT p.code
            FROM membership_roles mr
            JOIN role_permissions rp ON rp.role_id = mr.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE mr.membership_id = %s
            ORDER BY p.code
            """,
            (membership_id,),
        )
        rows = await cursor.fetchall()
        return {str(row["code"]) for row in rows}
