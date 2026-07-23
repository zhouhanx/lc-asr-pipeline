"""Resumable upload request and response schemas."""

from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

ArchiveType = Literal["zip", "tar", "tar.gz", "tgz"]
FileKind = Literal["audio", "image", "pdf"]


class UploadFileManifest(BaseModel):
    relative_path: str = Field(min_length=1, max_length=1024)
    size_bytes: int = Field(gt=0, le=5 * 1024**3)
    media_type: str | None = Field(default=None, max_length=160)
    archive_type: ArchiveType | None = None
    file_kind: FileKind = "audio"
    sha256: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{64}$")

    @field_validator("relative_path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        invalid_part = any(part in {"", "."} for part in path.parts)
        if path.is_absolute() or ".." in path.parts or invalid_part:
            raise ValueError("relative_path must be a safe relative path")
        return str(path)

    @model_validator(mode="after")
    def validate_kind(self) -> UploadFileManifest:
        suffix = self.relative_path.casefold()
        if self.file_kind == "pdf" and not suffix.endswith(".pdf"):
            raise ValueError("PDF uploads must use the .pdf extension")
        if self.file_kind == "image" and not suffix.endswith(
            (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
        ):
            raise ValueError("Image uploads use an unsupported extension")
        if self.file_kind != "audio" and self.archive_type is not None:
            raise ValueError("Document uploads cannot be archives")
        return self


class UploadBatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    files: list[UploadFileManifest] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def unique_paths(self) -> UploadBatchCreate:
        paths = [item.relative_path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("relative_path values must be unique")
        return self


class UploadFileResponse(BaseModel):
    id: UUID
    relative_path: str
    file_kind: FileKind
    size_bytes: int
    chunk_size: int
    expected_chunks: int
    received_chunks: int
    status: str
    deduplicated: bool = False


class UploadBatchResponse(BaseModel):
    id: UUID
    name: str
    total_bytes: int
    received_bytes: int
    file_count: int
    status: str
    created_at: datetime
    files: list[UploadFileResponse]


class UploadProgressResponse(BaseModel):
    file_id: UUID
    status: str
    expected_chunks: int
    received_chunks: list[int]


class UploadCompleteResponse(UploadProgressResponse):
    ready_file_ids: list[UUID]


class UploadCancelResponse(BaseModel):
    id: UUID
    status: str
    deleted_files: int


class HistoricalFileResponse(BaseModel):
    id: UUID
    original_name: str
    relative_path: str
    file_kind: FileKind
    size_bytes: int
    sha256: str
    created_at: datetime
    job_count: int = Field(ge=0)
    latest_job_id: UUID | None = None
    latest_job_status: str | None = None


class HistoricalFileDeleteResponse(BaseModel):
    id: UUID
    deleted_jobs: int = Field(ge=0)
    deleted_files: int = Field(ge=1)
