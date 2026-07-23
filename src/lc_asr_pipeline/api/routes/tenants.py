"""Tenant-scoped API routes."""

from typing import Annotated

from fastapi import APIRouter, Security

from lc_asr_pipeline.api.security import get_current_account
from lc_asr_pipeline.repositories.identity import Account
from lc_asr_pipeline.schemas.auth import TenantResponse

router = APIRouter(prefix="/tenants", tags=["tenants"])

TenantReader = Annotated[
    Account,
    Security(get_current_account, scopes=["tenant:read"]),
]


@router.get("/current", response_model=TenantResponse)
async def current_tenant(account: TenantReader) -> TenantResponse:
    """Return the current tenant when the membership can read tenant settings."""
    return TenantResponse(id=account.tenant_id, slug=account.tenant_slug, name=account.tenant_name)
