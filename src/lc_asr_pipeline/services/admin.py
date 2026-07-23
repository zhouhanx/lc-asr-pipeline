"""Platform administrator authentication and provisioning services."""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from anyio import to_thread
from psycopg.errors import UniqueViolation

from lc_asr_pipeline.core.config import Settings
from lc_asr_pipeline.core.security import (
    create_platform_admin_token,
    hash_password,
    validate_password_policy,
    verify_password,
)
from lc_asr_pipeline.db.pool import Database
from lc_asr_pipeline.repositories.admin import AdminRepository, PlatformAdmin
from lc_asr_pipeline.repositories.identity import IdentityRepository


class InvalidAdminCredentialsError(ValueError):
    pass


class DuplicateProvisioningError(ValueError):
    pass


class InvalidAdminCurrentPasswordError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AdminAuthResult:
    admin: PlatformAdmin
    access_token: str
    expires_at: datetime


class AdminService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self._database = database
        self._settings = settings
        self._repository = AdminRepository()

    async def login(self, username: str, password: str) -> AdminAuthResult:
        normalized_username = username.strip().casefold()
        async with self._database.connection() as connection:
            admin = await self._repository.find_by_username(connection, normalized_username)
        digest = admin.password_hash if admin else None
        valid = await to_thread.run_sync(verify_password, password, digest)
        if admin is None or not valid:
            raise InvalidAdminCredentialsError("Invalid administrator credentials")
        token, expires_at = create_platform_admin_token(
            settings=self._settings,
            admin_id=admin.id,
            password_change_only=admin.must_change_password,
        )
        async with self._database.connection() as connection:
            await self._repository.record_login(connection, admin.id)
        return AdminAuthResult(admin=admin, access_token=token, expires_at=expires_at)

    async def change_initial_password(
        self,
        admin_id: UUID,
        new_password: str,
    ) -> bool:
        async with self._database.connection() as connection:
            admin = await self._repository.find_active_by_id(connection, admin_id)
        if admin is None:
            return False
        validate_password_policy(new_password, admin.username)
        digest = await to_thread.run_sync(hash_password, new_password)
        async with self._database.connection() as connection:
            return await self._repository.change_password(
                connection,
                admin_id=admin_id,
                password_hash=digest,
            )

    async def change_password(
        self,
        admin: PlatformAdmin,
        *,
        current_password: str,
        new_password: str,
    ) -> bool:
        valid = await to_thread.run_sync(
            verify_password,
            current_password,
            admin.password_hash,
        )
        if not valid:
            raise InvalidAdminCurrentPasswordError("Current password is incorrect")
        validate_password_policy(new_password, admin.username)
        digest = await to_thread.run_sync(hash_password, new_password)
        async with self._database.connection() as connection:
            return await self._repository.replace_current_password(
                connection,
                admin_id=admin.id,
                password_hash=digest,
            )

    async def create_tenant(
        self,
        *,
        tenant_name: str,
        tenant_slug: str,
        owner_display_name: str,
        owner_email: str,
    ) -> tuple[dict[str, object], str]:
        initial_password = _initial_password()
        digest = await to_thread.run_sync(hash_password, initial_password)
        normalized_email = owner_email.strip().casefold()
        try:
            async with self._database.connection() as connection:
                account = await IdentityRepository().register_tenant_owner(
                    connection,
                    tenant_slug=tenant_slug,
                    tenant_name=tenant_name,
                    email=normalized_email,
                    display_name=owner_display_name,
                    password_hash=digest,
                    must_change_password=True,
                )
        except UniqueViolation as error:
            raise DuplicateProvisioningError("Tenant slug or email already exists") from error
        return {
            "tenant_id": account.tenant_id,
            "user_id": account.user_id,
        }, initial_password

    async def create_user(
        self,
        *,
        tenant_id: UUID,
        email: str,
        display_name: str,
        role: str,
    ) -> tuple[dict[str, object] | None, str]:
        initial_password = _initial_password()
        digest = await to_thread.run_sync(hash_password, initial_password)
        try:
            async with self._database.connection() as connection:
                user = await self._repository.add_tenant_user(
                    connection,
                    tenant_id=tenant_id,
                    email=email.strip().casefold(),
                    display_name=display_name,
                    password_hash=digest,
                    role=role,
                )
        except UniqueViolation as error:
            raise DuplicateProvisioningError("Email already exists") from error
        return user, initial_password

    async def reset_user_password(
        self,
        *,
        user_id: UUID,
    ) -> tuple[dict[str, object] | None, str]:
        initial_password = _initial_password()
        digest = await to_thread.run_sync(hash_password, initial_password)
        async with self._database.connection() as connection:
            user = await self._repository.reset_user_password(
                connection,
                user_id=user_id,
                password_hash=digest,
            )
        return user, initial_password


def _initial_password() -> str:
    characters = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%_-"),
    ]
    alphabet = string.ascii_letters + string.digits + "!@#$%_-"
    characters.extend(secrets.choice(alphabet) for _ in range(12))
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)
