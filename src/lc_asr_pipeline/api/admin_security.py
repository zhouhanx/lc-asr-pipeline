"""Authentication dependencies for the platform administrator boundary."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from lc_asr_pipeline.api.dependencies import DatabaseDependency, SettingsDependency
from lc_asr_pipeline.core.security import (
    InvalidAccessTokenError,
    decode_platform_admin_password_change_token,
    decode_platform_admin_token,
)
from lc_asr_pipeline.repositories.admin import AdminRepository, PlatformAdmin

admin_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/admin/auth/login")


async def _resolve_admin(
    token: str,
    database: DatabaseDependency,
    settings: SettingsDependency,
    password_change_only: bool = False,
) -> PlatformAdmin:
    try:
        claims = (
            decode_platform_admin_password_change_token(token, settings)
            if password_change_only
            else decode_platform_admin_token(token, settings)
        )
    except InvalidAccessTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired administrator token",
        ) from error
    async with database.system_connection() as connection:
        admin = await AdminRepository().find_active_by_id(connection, claims.admin_id)
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired administrator token",
        )
    return admin


async def get_platform_admin(
    token: Annotated[str, Depends(admin_oauth2_scheme)],
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> PlatformAdmin:
    admin = await _resolve_admin(token, database, settings)
    if admin.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator password change required",
        )
    return admin


async def get_initial_platform_admin(
    token: Annotated[str, Depends(admin_oauth2_scheme)],
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> PlatformAdmin:
    admin = await _resolve_admin(
        token,
        database,
        settings,
        password_change_only=True,
    )
    if not admin.must_change_password:
        raise HTTPException(status_code=409, detail="Initial password was already changed")
    return admin


CurrentPlatformAdmin = Annotated[PlatformAdmin, Depends(get_platform_admin)]
InitialPlatformAdmin = Annotated[PlatformAdmin, Depends(get_initial_platform_admin)]
