"""Unique identifiers for every platform HTTP operation."""

from __future__ import annotations

from uuid import UUID, uuid4

OPERATION_ID_HEADER = "X-Operation-ID"


def operation_reference(operation_uuid: UUID | None = None) -> str:
    """Return a new user-visible operation reference unless a UUID is supplied."""
    return f"OP-{operation_uuid or uuid4()}"
