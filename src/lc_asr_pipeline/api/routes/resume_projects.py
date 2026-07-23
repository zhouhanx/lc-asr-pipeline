"""Tenant resume-project knowledge endpoints."""

from typing import Annotated

from fastapi import APIRouter, Security

from lc_asr_pipeline.api.dependencies import DatabaseDependency
from lc_asr_pipeline.api.security import get_current_account
from lc_asr_pipeline.repositories.identity import Account
from lc_asr_pipeline.repositories.resume_projects import ResumeProjectRepository
from lc_asr_pipeline.schemas.resume_project import (
    ResumeProjectResponse,
    ResumeProjectSummary,
)

router = APIRouter(prefix="/resume-projects", tags=["resume-projects"])
repository = ResumeProjectRepository()
ResumeProjectReader = Annotated[
    Account,
    Security(get_current_account, scopes=["jobs:read"]),
]


@router.get("", response_model=list[ResumeProjectResponse])
async def list_resume_projects(
    account: ResumeProjectReader,
    database: DatabaseDependency,
) -> list[ResumeProjectResponse]:
    async with database.connection() as connection:
        rows = await repository.list_for_tenant(
            connection,
            tenant_id=account.tenant_id,
        )
    return [ResumeProjectResponse.model_validate(row) for row in rows]


@router.get("/summary", response_model=ResumeProjectSummary)
async def resume_project_summary(
    account: ResumeProjectReader,
    database: DatabaseDependency,
) -> ResumeProjectSummary:
    async with database.connection() as connection:
        row = await repository.summary(
            connection,
            tenant_id=account.tenant_id,
        )
    return ResumeProjectSummary.model_validate(row)
