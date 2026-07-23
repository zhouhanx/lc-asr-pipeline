"""Tenant model credential encryption tests."""

from uuid import uuid4

import pytest

from lc_asr_pipeline.services.model_secrets import (
    ModelSecretError,
    decrypt_model_secret,
    encrypt_model_secret,
)

MASTER_SECRET = "integration-master-secret-that-is-long-enough"


def test_model_secret_round_trip_is_tenant_bound_and_randomized() -> None:
    tenant_id = uuid4()
    first = encrypt_model_secret(
        "sk-tenant-secret",
        master_secret=MASTER_SECRET,
        tenant_id=tenant_id,
    )
    second = encrypt_model_secret(
        "sk-tenant-secret",
        master_secret=MASTER_SECRET,
        tenant_id=tenant_id,
    )

    assert first != second
    assert b"sk-tenant-secret" not in first
    assert decrypt_model_secret(
        first,
        master_secret=MASTER_SECRET,
        tenant_id=tenant_id,
    ) == "sk-tenant-secret"

    with pytest.raises(ModelSecretError):
        decrypt_model_secret(
            first,
            master_secret=MASTER_SECRET,
            tenant_id=uuid4(),
        )


def test_model_secret_rejects_tampering() -> None:
    tenant_id = uuid4()
    encrypted = bytearray(
        encrypt_model_secret(
            "sk-tenant-secret",
            master_secret=MASTER_SECRET,
            tenant_id=tenant_id,
        )
    )
    encrypted[-1] ^= 1

    with pytest.raises(ModelSecretError):
        decrypt_model_secret(
            bytes(encrypted),
            master_secret=MASTER_SECRET,
            tenant_id=tenant_id,
        )
