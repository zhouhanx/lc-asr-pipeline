"""Structured contracts for tenant resume authoring."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from lc_asr_pipeline.resume_templates import (
    DEFAULT_RESUME_TEMPLATE_KEY,
    RESUME_TEMPLATE_KEYS,
)


def validate_template_key(value: str) -> str:
    if value not in RESUME_TEMPLATE_KEYS:
        raise ValueError("unsupported resume template")
    return value


class ResumePersonalInfo(BaseModel):
    name: str = Field(default="", max_length=300)
    headline: str = Field(default="", max_length=300)
    phone: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=320)
    location: str = Field(default="", max_length=300)
    website: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=10000)


class ResumeEducationEntry(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    school: str = Field(default="", max_length=300)
    degree: str = Field(default="", max_length=300)
    major: str = Field(default="", max_length=300)
    start_date: str = Field(default="", max_length=40)
    end_date: str = Field(default="", max_length=40)
    description: str = Field(default="", max_length=10000)


class ResumeWorkEntry(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    company: str = Field(default="", max_length=300)
    role: str = Field(default="", max_length=300)
    start_date: str = Field(default="", max_length=40)
    end_date: str = Field(default="", max_length=40)
    highlights: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("highlights")
    @classmethod
    def validate_highlights(cls, values: list[str]) -> list[str]:
        if any(len(value) > 5000 for value in values):
            raise ValueError("work highlight is too long")
        return values


class ResumeProjectEntry(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    source_project_id: UUID | None = None
    name: str = Field(default="", max_length=300)
    company: str = Field(default="", max_length=300)
    role: str = Field(default="", max_length=300)
    start_date: str = Field(default="", max_length=40)
    end_date: str = Field(default="", max_length=40)
    summary: str = Field(default="", max_length=10000)
    highlights: list[str] = Field(default_factory=list, max_length=100)
    technologies: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("highlights", "technologies")
    @classmethod
    def validate_project_lists(cls, values: list[str]) -> list[str]:
        if any(len(value) > 5000 for value in values):
            raise ValueError("project item is too long")
        return values


class ResumeContent(BaseModel):
    personal: ResumePersonalInfo = Field(default_factory=ResumePersonalInfo)
    education: list[ResumeEducationEntry] = Field(default_factory=list, max_length=30)
    work: list[ResumeWorkEntry] = Field(default_factory=list, max_length=50)
    projects: list[ResumeProjectEntry] = Field(default_factory=list, max_length=100)
    skills: list[str] = Field(default_factory=list, max_length=200)
    certificates: list[str] = Field(default_factory=list, max_length=100)
    self_evaluation: str = Field(default="", max_length=20000)
    source_markdown: str = Field(default="", max_length=500000)

    @field_validator("skills", "certificates")
    @classmethod
    def validate_short_lists(cls, values: list[str]) -> list[str]:
        if any(len(value) > 1000 for value in values):
            raise ValueError("resume list item is too long")
        return values


class ResumeSourceResponse(BaseModel):
    id: UUID
    candidate_name: str
    source_path: str
    extracted_at: datetime
    project_count: int = Field(ge=0)
    draft_id: UUID | None = None


class ResumeDocumentCreate(BaseModel):
    source_resume_profile_id: UUID | None = None
    template_key: str = DEFAULT_RESUME_TEMPLATE_KEY

    _validate_template = field_validator("template_key")(validate_template_key)


class ResumeDocumentUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    template_key: str
    theme_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    content: ResumeContent

    _validate_template = field_validator("template_key")(validate_template_key)


class ResumeDocumentResponse(BaseModel):
    id: UUID
    source_resume_profile_id: UUID | None
    source_path: str | None
    title: str
    template_key: str
    theme_color: str
    content: ResumeContent
    has_photo: bool
    created_at: datetime
    updated_at: datetime


class ResumeTemplateResponse(BaseModel):
    key: str
    name: str
    description: str
    group: str
    layout: str
    header_style: str
    section_style: str
    density: str
    default_color: str
    variant: int
