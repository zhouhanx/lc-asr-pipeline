"""PostgreSQL row-level security and pooled tenant-context tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from psycopg.errors import InsufficientPrivilege

from lc_asr_pipeline.core.config import get_settings
from lc_asr_pipeline.db.migrate import run_migrations
from lc_asr_pipeline.db.pool import Database


@pytest.mark.integration
async def test_rls_defaults_deny_and_pool_context_does_not_leak() -> None:
    run_migrations()
    database = Database(get_settings())
    await database.open()
    suffix = uuid4().hex[:10]
    tenant_a_id = None
    tenant_b_id = None
    try:
        async with database.system_connection() as connection:
            tenant_a = await (
                await connection.execute(
                    """
                    INSERT INTO tenants (slug, name)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (f"rls-a-{suffix}", f"RLS A {suffix}"),
                )
            ).fetchone()
            tenant_b = await (
                await connection.execute(
                    """
                    INSERT INTO tenants (slug, name)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (f"rls-b-{suffix}", f"RLS B {suffix}"),
                )
            ).fetchone()
            assert tenant_a is not None and tenant_b is not None
            tenant_a_id = tenant_a["id"]
            tenant_b_id = tenant_b["id"]
            for tenant_id, label in ((tenant_a_id, "A"), (tenant_b_id, "B")):
                await connection.execute(
                    """
                    INSERT INTO model_providers (
                        tenant_id, name, provider_type, model_kind,
                        base_url, model_name, capabilities
                    )
                    VALUES (%s, %s, 'local', 'speech',
                            'http://127.0.0.1:8765', 'rls-model',
                            '["transcription"]'::jsonb)
                    """,
                    (tenant_id, f"RLS Provider {label} {suffix}"),
                )

        async with database.connection() as connection:
            state = await (
                await connection.execute(
                    """
                    SELECT current_user AS role_name,
                           row_security_active('model_providers') AS rls_active,
                           current_setting('app.tenant_id', true) AS tenant_context
                    """
                )
            ).fetchone()
            assert state is not None
            assert state["role_name"] == "lc_asr_app_runtime"
            assert state["rls_active"] is True
            assert state["tenant_context"] in (None, "")
            visible = await (
                await connection.execute("SELECT count(*) AS count FROM model_providers")
            ).fetchone()
            assert visible is not None and visible["count"] == 0

        async with database.tenant_connection(tenant_a_id) as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT tenant_id
                    FROM model_providers
                    WHERE name LIKE %s
                    ORDER BY name
                    """,
                    (f"RLS Provider % {suffix}",),
                )
            ).fetchall()
            assert [row["tenant_id"] for row in rows] == [tenant_a_id]
            hidden_update = await connection.execute(
                """
                UPDATE model_providers
                SET model_name = 'cross-tenant-write'
                WHERE tenant_id = %s
                """,
                (tenant_b_id,),
            )
            assert hidden_update.rowcount == 0

        with pytest.raises(InsufficientPrivilege):
            async with database.tenant_connection(tenant_a_id) as connection:
                await connection.execute(
                    """
                    INSERT INTO model_providers (
                        tenant_id, name, provider_type, model_kind,
                        base_url, model_name, capabilities
                    )
                    VALUES (%s, %s, 'local', 'speech',
                            'http://127.0.0.1:8765', 'forbidden',
                            '["transcription"]'::jsonb)
                    """,
                    (tenant_b_id, f"Forbidden {suffix}"),
                )

        async with database.connection() as connection:
            reset_state = await (
                await connection.execute(
                    """
                    SELECT current_user AS role_name,
                           current_setting('app.tenant_id', true) AS tenant_context,
                           (SELECT count(*) FROM model_providers) AS visible_count
                    """
                )
            ).fetchone()
            assert reset_state is not None
            assert reset_state["role_name"] == "lc_asr_app_runtime"
            assert reset_state["tenant_context"] in (None, "")
            assert reset_state["visible_count"] == 0

        async with database.system_connection() as connection:
            system_state = await (
                await connection.execute(
                    """
                    SELECT current_user AS role_name,
                           count(*) AS visible_count
                    FROM model_providers
                    WHERE name LIKE %s
                    GROUP BY current_user
                    """,
                    (f"RLS Provider % {suffix}",),
                )
            ).fetchone()
            assert system_state is not None
            assert system_state["role_name"] == "lc_asr_app_system"
            assert system_state["visible_count"] == 2
    finally:
        if tenant_a_id is not None and tenant_b_id is not None:
            async with database.system_connection() as connection:
                await connection.execute(
                    "DELETE FROM tenants WHERE id = ANY(%s)",
                    ([tenant_a_id, tenant_b_id],),
                )
        await database.close()
