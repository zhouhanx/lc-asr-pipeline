"""Tenant-aware authentication workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from anyio import to_thread
from psycopg import AsyncConnection

from lc_asr_pipeline.core.config import Settings
from lc_asr_pipeline.core.security import (
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    validate_password_policy,
    verify_password,
)
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.repositories.identity import Account, IdentityRepository
from lc_asr_pipeline.schemas.auth import LoginRequest


class InvalidCredentialsError(ValueError):
    """Raised when tenant-aware credentials cannot be authenticated."""


class InvalidRefreshTokenError(ValueError):
    """Raised when a refresh token is missing, expired, revoked, or unknown."""


class InvalidCurrentPasswordError(ValueError):
    """Raised when an authenticated user supplies the wrong current password."""


@dataclass(frozen=True, slots=True)
class AuthResult:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_session_id: UUID
    account: Account


class AuthService:
    """Coordinate secure identity workflows and transaction boundaries."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        repository: IdentityRepository | None = None,
    ) -> None:
        self._database = database
        self._settings = settings
        self._repository = repository or IdentityRepository()

    async def login(
        self,
        request: LoginRequest,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResult:
        normalized_email = str(request.email).strip().casefold()
        async with self._database.connection() as connection:
            login_account = await self._repository.find_login_account(
                connection,
                tenant_slug=request.tenant_slug,
                normalized_email=normalized_email,
            )

        password_digest = login_account.password_hash if login_account else None
        password_valid = await to_thread.run_sync(
            verify_password,
            request.password,
            password_digest,
        )
        if login_account is None or not password_valid:
            raise InvalidCredentialsError("Invalid tenant or credentials")

        async with self._database.connection() as connection:
            return await self._issue_session(
                connection=connection,
                account=login_account.account,
                user_agent=user_agent,
                ip_address=ip_address,
            )

    async def refresh(
        self,
        refresh_token: str,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResult:
        token_hash = hash_refresh_token(refresh_token)
        now = datetime.now(timezone.utc)
        async with self._database.connection() as connection:
            session = await self._repository.find_refresh_session_for_update(
                connection,
                token_hash=token_hash,
            )
            if session is None or session.revoked_at is not None or session.expires_at <= now:
                raise InvalidRefreshTokenError("Invalid refresh token")
            if session.account.must_change_password:
                raise InvalidRefreshTokenError("Initial password change required")

            result = await self._issue_session(
                connection=connection,
                account=session.account,
                user_agent=user_agent,
                ip_address=ip_address,
            )
            await self._repository.rotate_refresh_session(
                connection,
                old_session_id=session.id,
                new_session_id=result.refresh_session_id,
            )
            return result

    async def logout(self, refresh_token: str) -> None:
        async with self._database.connection() as connection:
            await self._repository.revoke_refresh_session(
                connection,
                token_hash=hash_refresh_token(refresh_token),
            )

    async def change_initial_password(self, account: Account, new_password: str) -> bool:
        validate_password_policy(new_password, account.email)
        password_digest = await to_thread.run_sync(hash_password, new_password)
        async with self._database.connection() as connection:
            return await self._repository.change_password(
                connection,
                account=account,
                password_hash=password_digest,
            )

    async def change_password(
        self,
        account: Account,
        *,
        current_password: str,
        new_password: str,
    ) -> bool:
        validate_password_policy(new_password, account.email)
        async with self._database.connection() as connection:
            current_digest = await self._repository.password_hash_for_account(
                connection,
                account=account,
            )
            valid = await to_thread.run_sync(
                verify_password,
                current_password,
                current_digest,
            )
            if current_digest is None or not valid:
                raise InvalidCurrentPasswordError("Current password is incorrect")
            password_digest = await to_thread.run_sync(hash_password, new_password)
            return await self._repository.replace_current_password(
                connection,
                account=account,
                password_hash=password_digest,
            )

    async def _issue_session(
        self,
        *,
        connection: AsyncConnection[dict[str, object]],
        account: Account,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthResult:
        access_token, access_expires_at = create_access_token(
            settings=self._settings,
            user_id=account.user_id,
            tenant_id=account.tenant_id,
            membership_id=account.membership_id,
            permissions=set(account.permissions),
            password_change_only=account.must_change_password,
        )
        refresh_token = new_refresh_token()
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(
            days=self._settings.auth_refresh_token_days
        )
        refresh_session_id = await self._repository.create_refresh_session(
            connection,
            account=account,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=refresh_expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        return AuthResult(
            access_token=access_token,
            access_expires_at=access_expires_at,
            refresh_token=refresh_token,
            refresh_session_id=refresh_session_id,
            account=account,
        )
