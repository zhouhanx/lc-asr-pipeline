"""Password, access-token, and refresh-token security primitives."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from lc_asr_pipeline.core.config import Settings

_password_hash = PasswordHash.recommended()
_dummy_hash = _password_hash.hash("lc-asr-pipeline-dummy-password")


class InvalidAccessTokenError(ValueError):
    """Raised when an access token cannot be trusted."""


class PasswordPolicyError(ValueError):
    """Raised when a new password does not meet the platform policy."""


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    tenant_id: UUID
    membership_id: UUID
    permissions: frozenset[str]
    token_id: UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class PlatformAdminClaims:
    admin_id: UUID
    token_id: UUID
    expires_at: datetime


def hash_password(password: str) -> str:
    """Hash a password using the configured modern Argon2 profile."""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password while preserving work for unknown accounts."""
    return _password_hash.verify(password, password_hash or _dummy_hash)


def validate_password_policy(password: str, login_identifier: str) -> None:
    """Require eight characters and either mixed case or a special character."""
    if len(password) < 8:
        raise PasswordPolicyError("Password must contain at least 8 characters")
    if len(password) > 128:
        raise PasswordPolicyError("Password must contain at most 128 characters")
    if password.casefold() == login_identifier.strip().casefold():
        raise PasswordPolicyError("Password cannot be the same as the login name")
    has_mixed_case = any(char.islower() for char in password) and any(
        char.isupper() for char in password
    )
    has_special = any(not char.isalnum() for char in password)
    if not has_mixed_case and not has_special:
        raise PasswordPolicyError(
            "Password must contain uppercase and lowercase letters or a special character"
        )


def create_access_token(
    *,
    settings: Settings,
    user_id: UUID,
    tenant_id: UUID,
    membership_id: UUID,
    permissions: set[str],
    password_change_only: bool = False,
) -> tuple[str, datetime]:
    """Create a short-lived signed access token."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.auth_access_token_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "membership_id": str(membership_id),
        "permissions": sorted(permissions),
        "jti": str(uuid4()),
        "iat": now,
        "exp": expires_at,
        "type": "password_change" if password_change_only else "access",
    }
    token = jwt.encode(
        payload,
        settings.auth_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return token, expires_at


def decode_access_token(token: str, settings: Settings) -> AccessClaims:
    """Verify and decode an access token into typed claims."""
    return _decode_tenant_token(token, settings, expected_type="access")


def decode_password_change_token(token: str, settings: Settings) -> AccessClaims:
    """Verify a token that is permanently limited to initial-password replacement."""
    return _decode_tenant_token(token, settings, expected_type="password_change")


def _decode_tenant_token(
    token: str,
    settings: Settings,
    *,
    expected_type: str,
) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "tenant_id", "membership_id", "jti", "iat", "exp", "type"]},
        )
        if payload.get("type") != expected_type:
            raise InvalidAccessTokenError("Unexpected token type")
        permissions = payload.get("permissions", [])
        if not isinstance(permissions, list) or not all(
            isinstance(permission, str) for permission in permissions
        ):
            raise InvalidAccessTokenError("Invalid permissions claim")
        expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=timezone.utc)
        return AccessClaims(
            user_id=UUID(str(payload["sub"])),
            tenant_id=UUID(str(payload["tenant_id"])),
            membership_id=UUID(str(payload["membership_id"])),
            permissions=frozenset(permissions),
            token_id=UUID(str(payload["jti"])),
            expires_at=expires_at,
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise InvalidAccessTokenError("Invalid access token") from error


def create_platform_admin_token(
    *,
    settings: Settings,
    admin_id: UUID,
    password_change_only: bool = False,
) -> tuple[str, datetime]:
    """Create a short-lived token that is valid only for platform administration."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.auth_access_token_minutes)
    payload: dict[str, Any] = {
        "sub": str(admin_id),
        "jti": str(uuid4()),
        "iat": now,
        "exp": expires_at,
        "type": (
            "platform_admin_password_change"
            if password_change_only
            else "platform_admin_access"
        ),
    }
    token = jwt.encode(
        payload,
        settings.auth_secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return token, expires_at


def decode_platform_admin_token(
    token: str,
    settings: Settings,
) -> PlatformAdminClaims:
    """Verify a platform-administrator token without accepting tenant tokens."""
    return _decode_platform_admin_token(
        token,
        settings,
        expected_type="platform_admin_access",
    )


def decode_platform_admin_password_change_token(
    token: str,
    settings: Settings,
) -> PlatformAdminClaims:
    """Verify a platform token permanently limited to initial-password replacement."""
    return _decode_platform_admin_token(
        token,
        settings,
        expected_type="platform_admin_password_change",
    )


def _decode_platform_admin_token(
    token: str,
    settings: Settings,
    *,
    expected_type: str,
) -> PlatformAdminClaims:
    try:
        payload = jwt.decode(
            token,
            settings.auth_secret_key.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "jti", "iat", "exp", "type"]},
        )
        if payload.get("type") != expected_type:
            raise InvalidAccessTokenError("Unexpected token type")
        return PlatformAdminClaims(
            admin_id=UUID(str(payload["sub"])),
            token_id=UUID(str(payload["jti"])),
            expires_at=datetime.fromtimestamp(float(payload["exp"]), tz=timezone.utc),
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError) as error:
        raise InvalidAccessTokenError("Invalid platform admin token") from error


def new_refresh_token() -> str:
    """Return a high-entropy opaque refresh token."""
    return secrets.token_urlsafe(64)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token before persistence."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
