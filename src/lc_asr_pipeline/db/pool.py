"""Async Psycopg connection pool lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from lc_asr_pipeline.core.config import Settings


class Database:
    """Own the application PostgreSQL connection pool."""

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
        """Yield a managed async connection."""
        async with self._pool.connection() as connection:
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
