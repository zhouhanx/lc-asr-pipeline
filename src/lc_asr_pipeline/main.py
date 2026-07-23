"""FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from lc_asr_pipeline.api.router import api_router
from lc_asr_pipeline.core.config import Settings, get_settings
from lc_asr_pipeline.db.pool import Database


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an application instance with explicit runtime dependencies."""
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(app_settings)
        app.state.settings = app_settings
        app.state.database = database
        await database.open()
        try:
            yield
        finally:
            await database.close()

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        debug=app_settings.app_debug,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-CSRF-Token",
            "X-Chunk-SHA256",
        ],
    )
    app.include_router(api_router, prefix=app_settings.api_prefix)
    return app


app = create_app()
