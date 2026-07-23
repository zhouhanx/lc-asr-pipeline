"""Platform-super-administrator API contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from lc_asr_pipeline.schemas.auth import TenantSlug
from lc_asr_pipeline.schemas.job import TranscriptionJobResponse, TranscriptSegmentResponse
from lc_asr_pipeline.schemas.model_provider import ModelProviderResponse
from lc_asr_pipeline.schemas.refinement import SpeakerMode


class PlatformAdminLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class PlatformAdminAuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    username: str
    password_change_required: bool


class PlatformAdminPasswordChangeRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class PlatformAdminCurrentPasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AdminTenantCreateRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=160)
    tenant_slug: TenantSlug
    owner_display_name: str = Field(min_length=2, max_length=120)
    owner_email: EmailStr


class AdminTenantUserCreateRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    role: Literal["owner", "admin", "member"] = "member"


class AdminUserStatusUpdateRequest(BaseModel):
    status: Literal["active", "disabled"]


class AdminTenantStatusUpdateRequest(BaseModel):
    status: Literal["active", "suspended"]


class AdminTenantDeleteResponse(BaseModel):
    id: UUID
    deleted_jobs: int = Field(ge=0)
    retained_recordings: int = Field(ge=0)
    status: Literal["deleted"]


class AdminUserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    tenant_name: str
    tenant_slug: str
    email: EmailStr
    display_name: str
    status: Literal["active", "disabled"]
    membership_status: str
    must_change_password: bool
    created_at: datetime


class AdminTenantResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    status: Literal["active", "suspended"]
    created_at: datetime
    users: list[AdminUserResponse]


class AdminProvisionedAccountResponse(BaseModel):
    tenant: AdminTenantResponse
    user: AdminUserResponse
    initial_password: str


class AdminProvisionedUserResponse(BaseModel):
    user: AdminUserResponse
    initial_password: str


class AdminResetUserPasswordResponse(BaseModel):
    user: AdminUserResponse
    initial_password: str


class AdminJobResponse(TranscriptionJobResponse):
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
    created_by_email: EmailStr
    created_by_name: str


class AdminJobDetail(AdminJobResponse):
    segments: list[TranscriptSegmentResponse] = Field(default_factory=list)


class AdminRecordingResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
    tenant_status: Literal["active", "suspended", "deleted"]
    original_name: str
    relative_path: str
    media_type: str | None
    size_bytes: int
    sha256: str | None
    created_at: datetime
    job_count: int = Field(ge=0)


class AdminRecordingModelsResponse(BaseModel):
    recording: AdminRecordingResponse
    models: list[ModelProviderResponse]


class AdminRecordingJobCreateRequest(BaseModel):
    provider_id: UUID
    text_provider_id: UUID
    language: str | None = Field(default=None, max_length=40)
    diarize: bool = True
    speaker_mode: SpeakerMode = "single"
