"""Tenant OCR job and result contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from lc_asr_pipeline.core.task_identity import task_reference

DocumentKind = Literal["image", "pdf"]
FileAttribute = Literal["resume", "document"]


class OCRJobCreate(BaseModel):
    ocr_provider_id: UUID
    text_provider_id: UUID
    uploaded_file_ids: list[UUID] = Field(min_length=1, max_length=100)
    document_kind: DocumentKind
    file_attribute: FileAttribute = "document"


class OCRJobResponse(BaseModel):
    id: UUID
    uploaded_file_id: UUID
    ocr_provider_id: UUID
    text_provider_id: UUID
    ocr_provider_name: str
    text_provider_name: str
    ocr_provider_deleted: bool
    text_provider_deleted: bool
    ocr_model_name: str
    text_model_name: str
    source_path: str
    document_kind: DocumentKind
    file_attribute: FileAttribute
    status: str
    progress_percent: int = Field(ge=0, le=100)
    attempts: int = Field(ge=0)
    refinement_attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    has_ocr_checkpoint: bool
    ocr_completed_at: datetime | None = None
    queued_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_id: UUID | None = None
    markdown_text: str | None = None
    page_count: int = Field(default=0, ge=0)
    error_message: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def task_id(self) -> str:
        return task_reference("ocr", self.id)


class OCRJobDetail(OCRJobResponse):
    raw_result: dict[str, Any] = Field(default_factory=dict)


class OCRJobDeleteResponse(BaseModel):
    id: UUID
    deleted_files: int = Field(ge=0)


class PaddleOCRResult(BaseModel):
    provider_job_id: str
    markdown_text: str
    page_count: int = Field(ge=0)
    raw_result: dict[str, Any]


class DocumentRefinementRequest(BaseModel):
    markdown_text: str = Field(min_length=1)
    document_kind: DocumentKind
    file_attribute: FileAttribute = "document"


class DocumentRefinementResult(BaseModel):
    markdown_text: str = Field(min_length=1)
    model: str
