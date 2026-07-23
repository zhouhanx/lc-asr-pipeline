"""Transcription job API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from lc_asr_pipeline.schemas.refinement import SpeakerMode


class TranscriptionJobCreate(BaseModel):
    provider_id: UUID
    text_provider_id: UUID
    uploaded_file_ids: list[UUID] = Field(min_length=1, max_length=10000)
    language: str | None = Field(default=None, max_length=40)
    diarize: bool = True
    speaker_mode: SpeakerMode = "single"


class TranscriptionJobResponse(BaseModel):
    id: UUID
    uploaded_file_id: UUID
    provider_id: UUID
    text_provider_id: UUID | None
    provider_name: str
    text_provider_name: str | None
    provider_deleted: bool
    text_provider_deleted: bool
    provider_type: str
    model_name: str
    text_model_name: str | None
    source_path: str
    status: str
    visibility: Literal["private", "public"]
    language: str | None
    diarize: bool
    speaker_mode: SpeakerMode
    progress_percent: int = Field(ge=0, le=100)
    attempts: int = Field(ge=0)
    refinement_attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    has_asr_checkpoint: bool
    asr_completed_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    error_message: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    transcript_id: UUID | None = None
    transcript_text: str | None = None


class TranscriptSegmentResponse(BaseModel):
    segment_index: int
    start_seconds: float
    end_seconds: float
    speaker: str | None
    text: str


class TranscriptionJobDetail(TranscriptionJobResponse):
    segments: list[TranscriptSegmentResponse] = Field(default_factory=list)


class TranscriptionJobVisibilityUpdate(BaseModel):
    visibility: Literal["private", "public"]


class PublicTranscriptionJobResponse(TranscriptionJobResponse):
    tenant_slug: str
    tenant_name: str


class PublicTranscriptionJobDetail(PublicTranscriptionJobResponse):
    segments: list[TranscriptSegmentResponse] = Field(default_factory=list)


class TranscriptionJobDeleteResponse(BaseModel):
    id: UUID
    deleted_jobs: int = Field(ge=1)
    deleted_files: int = Field(ge=0)
    source_deleted: bool
