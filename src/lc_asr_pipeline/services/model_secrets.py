"""Authenticated encryption for tenant-owned model credentials."""

from __future__ import annotations

import hashlib
import os
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_DOMAIN = b"lc-asr-pipeline:model-provider:v1\0"
_NONCE_BYTES = 12


class ModelSecretError(RuntimeError):
    """Raised when an encrypted provider credential cannot be decrypted."""


def _key(master_secret: str) -> bytes:
    if len(master_secret) < 32:
        raise ModelSecretError("Model secret master key is not configured safely")
    return hashlib.sha256(_DOMAIN + master_secret.encode("utf-8")).digest()


def encrypt_model_secret(secret: str, *, master_secret: str, tenant_id: UUID) -> bytes:
    """Encrypt one API key with a random nonce and tenant-bound associated data."""
    if not secret:
        raise ModelSecretError("Model API key cannot be empty")
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_key(master_secret)).encrypt(
        nonce,
        secret.encode("utf-8"),
        tenant_id.bytes,
    )
    return nonce + ciphertext


def decrypt_model_secret(
    encrypted: bytes | memoryview,
    *,
    master_secret: str,
    tenant_id: UUID,
) -> str:
    """Decrypt and authenticate one tenant-bound API key."""
    payload = bytes(encrypted)
    if len(payload) <= _NONCE_BYTES:
        raise ModelSecretError("Stored model credential is invalid")
    try:
        plaintext = AESGCM(_key(master_secret)).decrypt(
            payload[:_NONCE_BYTES],
            payload[_NONCE_BYTES:],
            tenant_id.bytes,
        )
    except (InvalidTag, ValueError) as exc:
        raise ModelSecretError("Stored model credential cannot be decrypted") from exc
    return plaintext.decode("utf-8")
