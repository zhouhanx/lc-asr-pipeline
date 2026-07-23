"""Tenant-aware registration, login, refresh, logout, and identity routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from lc_asr_pipeline.api.dependencies import DatabaseDependency, SettingsDependency
from lc_asr_pipeline.api.security import CurrentAccount, InitialPasswordAccount
from lc_asr_pipeline.core.security import PasswordPolicyError
from lc_asr_pipeline.repositories.identity import Account
from lc_asr_pipeline.schemas.auth import (
    AuthResponse,
    InitialPasswordChangeRequest,
    LoginRequest,
    MeResponse,
    MessageResponse,
    PasswordChangeRequest,
    TenantResponse,
    UserResponse,
)
from lc_asr_pipeline.services.auth import (
    AuthResult,
    AuthService,
    InvalidCredentialsError,
    InvalidCurrentPasswordError,
    InvalidRefreshTokenError,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _request_context(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address


def _set_refresh_cookie(
    response: Response, result: AuthResult, settings: SettingsDependency
) -> None:
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=result.refresh_token,
        max_age=settings.auth_refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        path=f"{settings.api_prefix}/auth",
    )


def _auth_response(result: AuthResult) -> AuthResponse:
    account = result.account
    return AuthResponse(
        access_token=result.access_token,
        expires_at=result.access_expires_at,
        user=_user_response(account),
        tenant=_tenant_response(account),
        permissions=sorted(account.permissions),
        password_change_required=account.must_change_password,
    )


def _user_response(account: Account) -> UserResponse:
    return UserResponse(
        id=account.user_id,
        email=account.email,
        display_name=account.display_name,
        email_verified=account.email_verified,
    )


def _tenant_response(account: Account) -> TenantResponse:
    return TenantResponse(
        id=account.tenant_id,
        slug=account.tenant_slug,
        name=account.tenant_name,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    """Authenticate an active membership within one tenant."""
    user_agent, ip_address = _request_context(request)
    try:
        result = await AuthService(database, settings).login(
            payload,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid tenant or credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    _set_refresh_cookie(response, result, settings)
    return _auth_response(result)


@router.post("/change-initial-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_initial_password(
    payload: InitialPasswordChangeRequest,
    account: InitialPasswordAccount,
    response: Response,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> None:
    try:
        changed = await AuthService(database, settings).change_initial_password(
            account,
            payload.new_password,
        )
    except PasswordPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not changed:
        raise HTTPException(status_code=409, detail="Initial password was already changed")
    response.delete_cookie(
        settings.auth_refresh_cookie_name,
        path=f"{settings.api_prefix}/auth",
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    account: CurrentAccount,
    response: Response,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> None:
    """Replace an established password only after verifying the current password."""
    try:
        changed = await AuthService(database, settings).change_password(
            account,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except InvalidCurrentPasswordError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except PasswordPolicyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if not changed:
        raise HTTPException(status_code=409, detail="Password could not be changed")
    response.delete_cookie(
        settings.auth_refresh_cookie_name,
        path=f"{settings.api_prefix}/auth",
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    """Rotate a valid refresh session and return a new access token."""
    refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )
    user_agent, ip_address = _request_context(request)
    try:
        result = await AuthService(database, settings).refresh(
            refresh_token,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    except InvalidRefreshTokenError as error:
        response.delete_cookie(
            settings.auth_refresh_cookie_name,
            path=f"{settings.api_prefix}/auth",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from error
    _set_refresh_cookie(response, result, settings)
    return _auth_response(result)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> MessageResponse:
    """Revoke the current refresh session and clear its cookie."""
    refresh_token = request.cookies.get(settings.auth_refresh_cookie_name)
    if refresh_token:
        await AuthService(database, settings).logout(refresh_token)
    response.delete_cookie(
        settings.auth_refresh_cookie_name,
        path=f"{settings.api_prefix}/auth",
    )
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=MeResponse)
async def me(account: CurrentAccount) -> MeResponse:
    """Return the authenticated tenant identity and current permissions."""
    return MeResponse(
        user=_user_response(account),
        tenant=_tenant_response(account),
        permissions=sorted(account.permissions),
    )
