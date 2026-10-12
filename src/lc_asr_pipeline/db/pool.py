"""Async Psycopg connection pool lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier
from psycopg_pool import AsyncConnectionPool

from lc_asr_pipeline.core.config import Settings


class Database:
    """Own the application PostgreSQL connection pool."""

    _runtime_role = "lc_asr_app_runtime"
    _system_role = "lc_asr_app_system"

    def __init__(self, settings: Settings) -> None:
        self._pool = cast(
            AsyncConnectionPool[AsyncConnection[dict[str, object]]],
            AsyncConnectionPool(
                conninfo=settings.postgres_conninfo,
                min_size=1,
                max_size=10,
                timeout=5,
                open=False,
                kwargs={"row_factory": dict_row},
            ),
        )

    async def open(self) -> None:
        """Start pool workers without making application startup depend on readiness."""
        await self._pool.open(wait=False)

    async def close(self) -> None:
        """Close all pool resources."""
        await self._pool.close()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
        """Yield a default-deny application connection without tenant context."""
        async with self._role_connection(self._runtime_role) as connection:
            yield connection

    @asynccontextmanager
    async def tenant_connection(
        self,
        tenant_id: UUID,
    ) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
        """Yield a transaction-scoped connection restricted to one tenant."""
        async with self._role_connection(self._runtime_role) as connection:
            await connection.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                (str(tenant_id),),
            )
            yield connection

    @asynccontextmanager
    async def system_connection(self) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
        """Yield an explicit cross-tenant connection for trusted platform work."""
        async with self._role_connection(self._system_role) as connection:
            yield connection

    @asynccontextmanager
    async def _role_connection(
        self,
        role_name: str,
    ) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
        """Set the least-privilege database role for one pooled transaction."""
        async with self._pool.connection() as connection:
            await connection.execute(
                SQL("SET LOCAL ROLE {}").format(Identifier(role_name)),
            )
            yield connection

    async def is_ready(self) -> bool:
        """Return whether PostgreSQL can execute a minimal query."""
        try:
            async with self.connection() as connection:
                cursor = await connection.execute("SELECT 1 AS ready")
                row = await cursor.fetchone()
            return bool(row and row["ready"] == 1)
        except Exception:
            return False
