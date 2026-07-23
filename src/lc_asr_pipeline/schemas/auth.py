"""Tenant-aware authentication API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, StringConstraints

TenantSlug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=3,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
    ),
]


class LoginRequest(BaseModel):
    tenant_slug: TenantSlug
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class InitialPasswordChangeRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    display_name: str
    email_verified: bool


class TenantResponse(BaseModel):
    id: UUID
    slug: str
    name: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse
    tenant: TenantResponse
    permissions: list[str]
    password_change_required: bool = False


class MeResponse(BaseModel):
    user: UserResponse
    tenant: TenantResponse
    permissions: list[str]


class MessageResponse(BaseModel):
    message: str
