"""FastAPI authentication and permission dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

from lc_asr_pipeline.api.dependencies import DatabaseDependency, SettingsDependency
from lc_asr_pipeline.core.security import (
    InvalidAccessTokenError,
    decode_access_token,
    decode_password_change_token,
)
from lc_asr_pipeline.repositories.identity import Account, IdentityRepository

PERMISSION_DESCRIPTIONS = {
    "workspace:read": "View the tenant workspace",
    "jobs:read": "View transcription jobs",
    "jobs:write": "Manage transcription jobs",
    "models:read": "View ASR models",
    "models:write": "Manage ASR models",
    "agents:read": "View agent workflows",
    "agents:write": "Manage agent workflows",
    "members:read": "View tenant members",
    "members:invite": "Invite tenant members",
    "members:manage": "Manage tenant members",
    "roles:read": "View tenant roles",
    "roles:manage": "Manage tenant roles",
    "tenant:read": "View tenant settings",
    "tenant:manage": "Manage tenant settings",
}

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    scopes=PERMISSION_DESCRIPTIONS,
)


async def get_current_account(
    security_scopes: SecurityScopes,
    token: Annotated[str, Depends(oauth2_scheme)],
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> Account:
    """Validate token claims, current membership state, and requested permissions."""
    authentication_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_access_token(token, settings)
    except InvalidAccessTokenError as error:
        raise authentication_error from error

    async with database.connection() as connection:
        account = await IdentityRepository().find_active_account(
            connection,
            user_id=claims.user_id,
            tenant_id=claims.tenant_id,
            membership_id=claims.membership_id,
        )
    if account is None:
        raise authentication_error
    if account.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Initial password change required",
        )

    required = set(security_scopes.scopes)
    if not required.issubset(account.permissions):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return account


CurrentAccount = Annotated[Account, Depends(get_current_account)]


async def get_initial_password_account(
    token: Annotated[str, Depends(oauth2_scheme)],
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> Account:
    """Accept a valid tenant token only for completing an initial password change."""
    try:
        claims = decode_password_change_token(token, settings)
    except InvalidAccessTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        ) from error
    async with database.connection() as connection:
        account = await IdentityRepository().find_active_account(
            connection,
            user_id=claims.user_id,
            tenant_id=claims.tenant_id,
            membership_id=claims.membership_id,
        )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )
    if not account.must_change_password:
        raise HTTPException(status_code=409, detail="Initial password was already changed")
    return account


InitialPasswordAccount = Annotated[Account, Depends(get_initial_password_account)]
