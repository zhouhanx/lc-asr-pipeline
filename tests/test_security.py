"""Authentication security primitive tests."""

import pytest
from pydantic import SecretStr

from lc_asr_pipeline.core.config import Settings
from lc_asr_pipeline.core.security import (
    InvalidAccessTokenError,
    PasswordPolicyError,
    create_access_token,
    create_platform_admin_token,
    decode_access_token,
    decode_password_change_token,
    decode_platform_admin_password_change_token,
    decode_platform_admin_token,
    hash_password,
    validate_password_policy,
    verify_password,
)


def test_argon2_password_round_trip() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert password_hash.startswith("$argon2")
    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


@pytest.mark.parametrize("password", ["Abcdefg1", "abcdefgh!"])
def test_password_policy_accepts_mixed_case_or_special_character(password: str) -> None:
    validate_password_policy(password, "owner@example.com")


@pytest.mark.parametrize(
    "password,login",
    [
        ("Abcdef1", "owner@example.com"),
        ("abcdefgh", "owner@example.com"),
        ("owner@example.com", "owner@example.com"),
    ],
)
def test_password_policy_rejects_invalid_password(password: str, login: str) -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password_policy(password, login)


def test_access_token_round_trip() -> None:
    from uuid import uuid4

    settings = Settings(
        postgres_user="test",
        postgres_password=SecretStr("test"),
        postgres_database="test",
        auth_secret_key=SecretStr("test-secret-that-is-long-enough-for-unit-tests"),
    )
    user_id = uuid4()
    tenant_id = uuid4()
    membership_id = uuid4()

    token, _ = create_access_token(
        settings=settings,
        user_id=user_id,
        tenant_id=tenant_id,
        membership_id=membership_id,
        permissions={"workspace:read"},
    )
    claims = decode_access_token(token, settings)

    assert claims.user_id == user_id
    assert claims.tenant_id == tenant_id
    assert claims.membership_id == membership_id
    assert claims.permissions == frozenset({"workspace:read"})


def test_platform_admin_token_cannot_cross_tenant_token_boundary() -> None:
    from uuid import uuid4

    settings = Settings(
        postgres_user="test",
        postgres_password=SecretStr("test"),
        postgres_database="test",
        auth_secret_key=SecretStr("test-secret-that-is-long-enough-for-unit-tests"),
    )
    admin_id = uuid4()
    token, _ = create_platform_admin_token(settings=settings, admin_id=admin_id)

    assert decode_platform_admin_token(token, settings).admin_id == admin_id
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, settings)


def test_password_change_tokens_never_become_normal_access_tokens() -> None:
    from uuid import uuid4

    settings = Settings(
        postgres_user="test",
        postgres_password=SecretStr("test"),
        postgres_database="test",
        auth_secret_key=SecretStr("test-secret-that-is-long-enough-for-unit-tests"),
    )
    tenant_token, _ = create_access_token(
        settings=settings,
        user_id=uuid4(),
        tenant_id=uuid4(),
        membership_id=uuid4(),
        permissions={"workspace:read"},
        password_change_only=True,
    )
    decode_password_change_token(tenant_token, settings)
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(tenant_token, settings)

    admin_token, _ = create_platform_admin_token(
        settings=settings,
        admin_id=uuid4(),
        password_change_only=True,
    )
    decode_platform_admin_password_change_token(admin_token, settings)
    with pytest.raises(InvalidAccessTokenError):
        decode_platform_admin_token(admin_token, settings)
