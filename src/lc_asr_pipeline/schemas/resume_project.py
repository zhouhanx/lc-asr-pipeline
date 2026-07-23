"""Structured resume project extraction and tenant API contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ProjectScoreDimension(BaseModel):
    score: int = Field(ge=1, le=10)
    reason: str = Field(min_length=1, max_length=2000)


class ProjectScoring(BaseModel):
    architecture_rationality: ProjectScoreDimension
    description_credibility: ProjectScoreDimension
    embellishment_risk: ProjectScoreDimension


class ExtractedResumeProject(BaseModel):
    project_name: str = Field(min_length=1, max_length=300)
    company_name: str | None = Field(default=None, max_length=300)
    role_name: str | None = Field(default=None, max_length=300)
    start_date: str | None = Field(default=None, max_length=40)
    end_date: str | None = Field(default=None, max_length=40)
    is_current: bool = False
    description: str | None = None
    responsibilities: list[str] = Field(default_factory=list, max_length=100)
    technologies: list[str] = Field(default_factory=list, max_length=100)
    project_background: str | None = None
    project_responsibilities: list[str] = Field(default_factory=list, max_length=100)
    project_outcomes: list[str] = Field(default_factory=list, max_length=100)
    scoring: ProjectScoring
    source_excerpt: str | None = Field(default=None, max_length=2000)

    @field_validator("project_name", mode="before")
    @classmethod
    def normalize_missing_project_name(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return "未命名项目"
        return value

    @field_validator(
        "responsibilities",
        "technologies",
        "project_responsibilities",
        "project_outcomes",
        mode="before",
    )
    @classmethod
    def normalize_missing_lists(cls, value: object) -> object:
        return [] if value is None else value


class ResumeProjectExtraction(BaseModel):
    candidate_name: str = Field(default="未识别姓名", min_length=1, max_length=300)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    current_company: str | None = Field(default=None, max_length=300)
    projects: list[ExtractedResumeProject] = Field(default_factory=list, max_length=100)
    model: str

    @field_validator("candidate_name", mode="before")
    @classmethod
    def normalize_missing_candidate_name(cls, value: object) -> object:
        if value is None or (isinstance(value, str) and not value.strip()):
            return "未识别姓名"
        return value


class ResumeProjectExtractionRequest(BaseModel):
    markdown_text: str = Field(min_length=1)


class ResumeProjectResponse(BaseModel):
    id: UUID
    resume_profile_id: UUID
    ocr_job_id: UUID
    uploaded_file_id: UUID
    candidate_name: str
    phone: str | None
    email: str | None
    project_index: int = Field(ge=0)
    project_name: str
    company_name: str | None
    role_name: str | None
    start_date: str | None
    end_date: str | None
    is_current: bool
    description: str | None
    responsibilities: list[str]
    technologies: list[str]
    project_background: str | None
    project_responsibilities: list[str]
    project_outcomes: list[str]
    architecture_score: int | None = Field(default=None, ge=1, le=10)
    architecture_reason: str | None
    credibility_score: int | None = Field(default=None, ge=1, le=10)
    credibility_reason: str | None
    embellishment_risk_score: int | None = Field(default=None, ge=1, le=10)
    embellishment_risk_reason: str | None
    overall_score: float | None
    source_excerpt: str | None
    source_path: str
    extraction_model_name: str
    ocr_completed_at: datetime | None
    extracted_at: datetime


class ResumeProjectSummary(BaseModel):
    project_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    company_count: int = Field(ge=0)
