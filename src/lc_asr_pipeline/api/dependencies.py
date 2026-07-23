"""Shared FastAPI dependencies."""

from typing import Annotated, cast

from fastapi import Depends, Request

from lc_asr_pipeline.core.config import Settings
from lc_asr_pipeline.db.pool import Database


def get_database(request: Request) -> Database:
    """Return the application database service."""
    return cast(Database, request.app.state.database)


DatabaseDependency = Annotated[Database, Depends(get_database)]


def get_runtime_settings(request: Request) -> Settings:
    """Return the settings attached during application startup."""
    return cast(Settings, request.app.state.settings)


SettingsDependency = Annotated[Settings, Depends(get_runtime_settings)]
