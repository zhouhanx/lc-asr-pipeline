"""Tenant OCR job endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, Security, status

from lc_asr_pipeline.api.dependencies import DatabaseDependency
from lc_asr_pipeline.api.security import get_current_account
from lc_asr_pipeline.repositories.identity import Account
from lc_asr_pipeline.repositories.ocr_jobs import OCRJobRepository
from lc_asr_pipeline.schemas.ocr import (
    OCRJobCreate,
    OCRJobDeleteResponse,
    OCRJobDetail,
    OCRJobResponse,
)

router = APIRouter(prefix="/ocr/jobs", tags=["ocr"])
repository = OCRJobRepository()
OCRReader = Annotated[Account, Security(get_current_account, scopes=["jobs:read"])]
OCRWriter = Annotated[Account, Security(get_current_account, scopes=["jobs:write"])]


@router.get("", response_model=list[OCRJobResponse])
async def list_ocr_jobs(
    account: OCRReader,
    database: DatabaseDependency,
) -> list[OCRJobResponse]:
    async with database.connection() as connection:
        rows = await repository.list_for_tenant(
            connection,
            tenant_id=account.tenant_id,
        )
    return [OCRJobResponse.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=list[OCRJobResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_ocr_jobs(
    payload: OCRJobCreate,
    account: OCRWriter,
    database: DatabaseDependency,
) -> list[OCRJobResponse]:
    async with database.connection() as connection:
        rows = await repository.create_jobs(
            connection,
            tenant_id=account.tenant_id,
            user_id=account.user_id,
            ocr_provider_id=payload.ocr_provider_id,
            text_provider_id=payload.text_provider_id,
            file_ids=payload.uploaded_file_ids,
            document_kind=payload.document_kind,
            file_attribute=payload.file_attribute,
        )
    if len(rows) != len(payload.uploaded_file_ids):
        raise HTTPException(
            status_code=422,
            detail=(
                f"OCR/text model or ready document selection is invalid for {payload.document_kind}"
            ),
        )
    return [OCRJobResponse.model_validate(row) for row in rows]


@router.get("/{job_id}", response_model=OCRJobDetail)
async def ocr_job_detail(
    job_id: UUID,
    account: OCRReader,
    database: DatabaseDependency,
) -> OCRJobDetail:
    async with database.connection() as connection:
        row = await repository.get_for_tenant(
            connection,
            tenant_id=account.tenant_id,
            job_id=job_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="OCR job not found")
    return OCRJobDetail.model_validate(row)


@router.post("/{job_id}/cancel", response_model=OCRJobResponse)
async def cancel_ocr_job(
    job_id: UUID,
    account: OCRWriter,
    database: DatabaseDependency,
) -> OCRJobResponse:
    async with database.connection() as connection:
        row = await repository.request_cancel(
            connection,
            tenant_id=account.tenant_id,
            job_id=job_id,
        )
    if row is None:
        raise HTTPException(status_code=409, detail="OCR job cannot be cancelled")
    return OCRJobResponse.model_validate(row)


@router.post("/{job_id}/retry", response_model=OCRJobResponse)
async def retry_ocr_job(
    job_id: UUID,
    account: OCRWriter,
    database: DatabaseDependency,
) -> OCRJobResponse:
    async with database.connection() as connection:
        row = await repository.retry(
            connection,
            tenant_id=account.tenant_id,
            job_id=job_id,
        )
    if row is None:
        raise HTTPException(status_code=409, detail="OCR job cannot be retried")
    return OCRJobResponse.model_validate(row)


@router.delete("/{job_id}", response_model=OCRJobDeleteResponse)
async def delete_ocr_job(
    job_id: UUID,
    account: OCRWriter,
    database: DatabaseDependency,
) -> OCRJobDeleteResponse:
    async with database.connection() as connection:
        result = await repository.delete(
            connection,
            tenant_id=account.tenant_id,
            job_id=job_id,
        )
    if result == "not_found":
        raise HTTPException(status_code=404, detail="OCR job not found")
    if result == "active":
        raise HTTPException(status_code=409, detail="Active OCR job cannot be deleted")
    return OCRJobDeleteResponse(id=job_id, deleted_files=0)


@router.get("/{job_id}/export/{export_format}")
async def export_ocr_job(
    job_id: UUID,
    export_format: str,
    account: OCRReader,
    database: DatabaseDependency,
) -> Response:
    if export_format not in {"md", "json"}:
        raise HTTPException(status_code=422, detail="Unsupported OCR export format")
    async with database.connection() as connection:
        row = await repository.get_for_tenant(
            connection,
            tenant_id=account.tenant_id,
            job_id=job_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="OCR job not found")
    if row["status"] != "completed" or not row["markdown_text"]:
        raise HTTPException(status_code=409, detail="OCR result is not complete")
    if export_format == "json":
        detail = OCRJobDetail.model_validate(row)
        content = detail.model_dump_json(indent=2).encode()
        media_type = "application/json"
    else:
        content = str(row["markdown_text"]).encode()
        media_type = "text/markdown; charset=utf-8"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": (f'attachment; filename="ocr-{job_id}.{export_format}"')},
    )
