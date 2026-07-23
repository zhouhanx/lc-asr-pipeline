"""Tenant-scoped workspace metrics."""

from typing import Annotated

from fastapi import APIRouter, Security

from lc_asr_pipeline.api.dependencies import DatabaseDependency
from lc_asr_pipeline.api.security import get_current_account
from lc_asr_pipeline.repositories.identity import Account
from lc_asr_pipeline.schemas.workspace import WorkspaceSummary

router = APIRouter(prefix="/workspace", tags=["workspace"])
WorkspaceReader = Annotated[
    Account,
    Security(get_current_account, scopes=["workspace:read"]),
]


@router.get("/summary", response_model=WorkspaceSummary)
async def workspace_summary(
    account: WorkspaceReader,
    database: DatabaseDependency,
) -> WorkspaceSummary:
    async with database.connection() as connection:
        row = await (
            await connection.execute(
                """
                SELECT
                    count(*) FILTER (
                        WHERE status IN ('processing', 'refining')
                    ) AS running_tasks,
                    count(*) FILTER (WHERE status = 'queued') AS queued_tasks,
                    count(*) FILTER (WHERE status = 'completed') AS completed_tasks,
                    (SELECT count(*) FROM model_providers
                     WHERE tenant_id = %s AND is_enabled AND deleted_at IS NULL)
                        AS available_models,
                    (SELECT count(DISTINCT sha256) FROM uploaded_files
                     WHERE tenant_id = %s AND status = 'ready'
                       AND sha256 IS NOT NULL AND archive_type IS NULL) AS historical_files
                FROM transcription_jobs
                WHERE tenant_id = %s
                """,
                (account.tenant_id, account.tenant_id, account.tenant_id),
            )
        ).fetchone()
    assert row is not None
    return WorkspaceSummary.model_validate(row)
