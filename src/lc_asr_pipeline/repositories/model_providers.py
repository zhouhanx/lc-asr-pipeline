"""Tenant-scoped model provider persistence."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb


class ModelProviderRepository:
    async def get_for_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        provider_id: UUID,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                """
                SELECT id, name, provider_type, model_kind, base_url, model_name,
                       api_key_env, api_key_ciphertext, capabilities, is_enabled,
                       is_default, is_system, created_at,
                       (api_key_ciphertext IS NOT NULL OR api_key_env IS NOT NULL) AS has_api_key
                FROM model_providers
                WHERE id = %s AND tenant_id = %s AND deleted_at IS NULL
                """,
                (provider_id, tenant_id),
            )
        ).fetchone()
        return None if row is None else dict(row)

    async def list_for_tenant(
        self,
        connection: AsyncConnection[dict[str, object]],
        tenant_id: UUID,
    ) -> list[dict[str, Any]]:
        cursor = await connection.execute(
            """
            SELECT id, name, provider_type, model_kind, base_url, model_name, capabilities,
                   is_enabled, is_default, is_system, created_at,
                   (api_key_ciphertext IS NOT NULL OR api_key_env IS NOT NULL) AS has_api_key
            FROM model_providers
            WHERE tenant_id = %s AND deleted_at IS NULL
            ORDER BY model_kind, is_default DESC, name
            """,
            (tenant_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def create(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        name: str,
        model_kind: str,
        provider_type: str,
        base_url: str,
        model_name: str,
        api_key_ciphertext: bytes,
        capabilities: list[str],
    ) -> dict[str, Any]:
        row = await (
            await connection.execute(
                """
                INSERT INTO model_providers (
                    tenant_id, name, model_kind, provider_type, base_url, model_name,
                    api_key_ciphertext, capabilities
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, provider_type, model_kind, base_url, model_name,
                          capabilities, is_enabled, is_default, is_system, created_at,
                          true AS has_api_key
                """,
                (
                    tenant_id,
                    name,
                    model_kind,
                    provider_type,
                    base_url,
                    model_name,
                    api_key_ciphertext,
                    Jsonb(capabilities),
                ),
            )
        ).fetchone()
        assert row is not None
        return dict(row)

    async def update(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        provider_id: UUID,
        name: str,
        base_url: str,
        model_name: str,
        api_key_ciphertext: bytes | None,
    ) -> dict[str, Any] | None:
        row = await (
            await connection.execute(
                """
                UPDATE model_providers
                SET name = %s, base_url = %s, model_name = %s,
                    api_key_ciphertext = COALESCE(%s, api_key_ciphertext),
                    api_key_env = CASE WHEN %s IS NULL THEN api_key_env ELSE NULL END,
                    updated_at = now()
                WHERE id = %s AND tenant_id = %s AND NOT is_system
                  AND deleted_at IS NULL
                RETURNING id
                """,
                (
                    name,
                    base_url,
                    model_name,
                    api_key_ciphertext,
                    api_key_ciphertext,
                    provider_id,
                    tenant_id,
                ),
            )
        ).fetchone()
        if row is None:
            return None
        return await self.get_for_tenant(
            connection,
            tenant_id=tenant_id,
            provider_id=provider_id,
        )

    async def delete(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        provider_id: UUID,
    ) -> str:
        """Hide a tenant model while preserving historical job lineage."""
        provider = await (
            await connection.execute(
                """
                SELECT id
                FROM model_providers
                WHERE id = %s AND tenant_id = %s AND deleted_at IS NULL
                FOR UPDATE
                """,
                (provider_id, tenant_id),
            )
        ).fetchone()
        if provider is None:
            return "not_found"
        await connection.execute(
            """
            UPDATE model_providers
            SET deleted_at = now(), is_enabled = false, is_default = false,
                updated_at = now()
            WHERE id = %s AND tenant_id = %s
            """,
            (provider_id, tenant_id),
        )
        return "deleted"

    async def set_default(
        self,
        connection: AsyncConnection[dict[str, object]],
        *,
        tenant_id: UUID,
        provider_id: UUID,
    ) -> dict[str, Any] | None:
        target = await (
            await connection.execute(
                """
                SELECT id, model_kind FROM model_providers
                WHERE id = %s AND tenant_id = %s AND is_enabled
                  AND deleted_at IS NULL
                FOR UPDATE
                """,
                (provider_id, tenant_id),
            )
        ).fetchone()
        if target is None:
            return None
        await connection.execute(
            """
            UPDATE model_providers SET is_default = false, updated_at = now()
            WHERE tenant_id = %s AND model_kind = %s AND deleted_at IS NULL
            """,
            (tenant_id, target["model_kind"]),
        )
        await connection.execute(
            "UPDATE model_providers SET is_default = true, updated_at = now() WHERE id = %s",
            (provider_id,),
        )
        return await self.get_for_tenant(
            connection,
            tenant_id=tenant_id,
            provider_id=provider_id,
        )
