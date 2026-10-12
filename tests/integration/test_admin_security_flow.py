"""Persistent platform-admin login protection and security-header tests."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from lc_asr_pipeline.core.config import get_settings
from lc_asr_pipeline.core.security import admin_login_fingerprint, hash_password
from lc_asr_pipeline.main import create_app


@pytest.mark.integration
async def test_admin_account_lock_is_persistent_and_non_enumerating() -> None:
    suffix = uuid4().hex[:10]
    username = f"locked-{suffix}"
    password = "Admin-Lock-Test-42!"
    settings = get_settings().model_copy(
        update={
            "admin_login_account_max_failures": 3,
            "admin_login_source_max_attempts": 100,
            "admin_login_identity_source_max_attempts": 100,
            "admin_login_window_seconds": 300,
            "admin_login_lock_seconds": 120,
        }
    )
    secure_app = create_app(settings)
    async with secure_app.router.lifespan_context(secure_app):
        database = secure_app.state.database
        async with database.system_connection() as connection:
            await connection.execute(
                """
                INSERT INTO platform_admins (username, password_hash, must_change_password)
                VALUES (%s, %s, false)
                """,
                (username, hash_password(password)),
            )
        transport = httpx.ASGITransport(
            app=secure_app,
            client=("192.0.2.10", 41000),
        )
        try:
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                for attempt in range(3):
                    response = await client.post(
                        "/api/v1/admin/auth/login",
                        json={"username": username, "password": "wrong-password"},
                    )
                    expected = 429 if attempt == 2 else 401
                    assert response.status_code == expected
                    assert response.json()["detail"] in {
                        "Invalid administrator credentials",
                        "Administrator login temporarily unavailable",
                    }
                    assert response.headers["cache-control"] == "no-store"
                    assert response.headers["x-content-type-options"] == "nosniff"
                    assert response.headers["x-frame-options"] == "DENY"
                    assert "strict-transport-security" not in response.headers

                blocked_correct_password = await client.post(
                    "/api/v1/admin/auth/login",
                    json={"username": username, "password": password},
                )
                assert blocked_correct_password.status_code == 429
                assert int(blocked_correct_password.headers["retry-after"]) >= 1

                async with database.system_connection() as connection:
                    state = await (
                        await connection.execute(
                            """
                            SELECT failed_login_attempts, locked_until > now() AS locked
                            FROM platform_admins
                            WHERE username = %s
                            """,
                            (username,),
                        )
                    ).fetchone()
                    assert state is not None
                    assert state["failed_login_attempts"] == 3
                    assert state["locked"] is True
                    fingerprints = await (
                        await connection.execute(
                            """
                            SELECT key_hash
                            FROM platform_admin_login_limits
                            """
                        )
                    ).fetchall()
                    assert fingerprints
                    assert all(len(str(row["key_hash"])) == 64 for row in fingerprints)
                    assert all("192.0.2.10" not in str(row["key_hash"]) for row in fingerprints)
                    await connection.execute(
                        """
                        UPDATE platform_admins
                        SET locked_until = now() - interval '1 second',
                            failed_login_attempts = 0,
                            failed_login_window_started_at = NULL
                        WHERE username = %s
                        """,
                        (username,),
                    )

                recovered = await client.post(
                    "/api/v1/admin/auth/login",
                    json={"username": username, "password": password},
                )
                assert recovered.status_code == 200, recovered.text
        finally:
            async with database.system_connection() as connection:
                await connection.execute(
                    "DELETE FROM platform_admins WHERE username = %s",
                    (username,),
                )
                source_key = admin_login_fingerprint("source:192.0.2.10", settings)
                identity_key = admin_login_fingerprint(
                    f"identity_source:{username}:192.0.2.10",
                    settings,
                )
                await connection.execute(
                    """
                    DELETE FROM platform_admin_login_limits
                    WHERE key_hash = ANY(%s)
                    """,
                    ([source_key, identity_key],),
                )


@pytest.mark.integration
async def test_unknown_admins_are_limited_by_source_and_production_uses_hsts() -> None:
    settings = get_settings().model_copy(
        update={
            "app_env": "production",
            "admin_login_source_max_attempts": 5,
            "admin_login_identity_source_max_attempts": 100,
            "admin_login_window_seconds": 300,
            "admin_login_lock_seconds": 120,
        }
    )
    secure_app = create_app(settings)
    async with secure_app.router.lifespan_context(secure_app):
        database = secure_app.state.database
        transport = httpx.ASGITransport(
            app=secure_app,
            client=("192.0.2.20", 42000),
        )
        try:
            async with httpx.AsyncClient(
                transport=transport,
                base_url="https://testserver",
            ) as client:
                statuses = []
                for index in range(6):
                    response = await client.post(
                        "/api/v1/admin/auth/login",
                        json={
                            "username": f"missing-{index}",
                            "password": "wrong-password",
                        },
                    )
                    statuses.append(response.status_code)
                assert statuses == [401, 401, 401, 401, 401, 429]
                assert response.headers["strict-transport-security"].startswith("max-age=")
                assert response.json()["detail"] == ("Administrator login temporarily unavailable")
        finally:
            async with database.system_connection() as connection:
                source_key = admin_login_fingerprint("source:192.0.2.20", settings)
                identity_keys = [
                    admin_login_fingerprint(
                        f"identity_source:missing-{index}:192.0.2.20",
                        settings,
                    )
                    for index in range(6)
                ]
                await connection.execute(
                    """
                    DELETE FROM platform_admin_login_limits
                    WHERE key_hash = ANY(%s)
                    """,
                    ([source_key, *identity_keys],),
                )
