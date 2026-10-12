"""Environment-backed secret reference resolution."""

from __future__ import annotations

import os

from dotenv import dotenv_values


def resolve_secret_reference(name: str | None) -> str:
    if not name:
        return ""
    values = dotenv_values(".env")
    return os.getenv(name) or values.get(name) or ""
