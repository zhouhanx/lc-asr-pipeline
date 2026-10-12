"""Tenant resume-writing APIs and exports."""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, Security, status

from lc_asr_pipeline.api.dependencies import DatabaseDependency, SettingsDependency
from lc_asr_pipeline.api.security import get_current_account
from lc_asr_pipeline.repositories.identity import Account
from lc_asr_pipeline.repositories.resume_writer import ResumeWriterRepository
from lc_asr_pipeline.resume_templates import RESUME_TEMPLATES
from lc_asr_pipeline.schemas.resume_writer import (
    ResumeDocumentCreate,
    ResumeDocumentResponse,
    ResumeDocumentUpdate,
    ResumeSourceResponse,
    ResumeTemplateResponse,
)
from lc_asr_pipeline.services.image_security import (
    MAX_RESUME_PHOTO_BYTES,
    UnsafeImageError,
    normalize_resume_photo,
)
from lc_asr_pipeline.services.resume_export import render_resume_html, render_resume_pdf

router = APIRouter(prefix="/resume-writer", tags=["resume-writer"])
repository = ResumeWriterRepository()
ResumeWriterReader = Annotated[
    Account,
    Security(get_current_account, scopes=["jobs:read"]),
]
ResumeWriterEditor = Annotated[
    Account,
    Security(get_current_account, scopes=["jobs:write"]),
]
_PDF_EXPORT_LIMIT = asyncio.Semaphore(2)


def _validate_photo(media_type: str, image_bytes: bytes) -> None:
    try:
        normalize_resume_photo(media_type, image_bytes)
    except UnsafeImageError as error:
        status_code = 413 if not image_bytes or len(image_bytes) > MAX_RESUME_PHOTO_BYTES else 422
        raise HTTPException(
            status_code=status_code,
            detail="照片无效；仅支持安全的单帧 JPG、PNG 或 WebP",
        ) from error


@router.get("/templates", response_model=list[ResumeTemplateResponse])
async def list_resume_templates(
    _account: ResumeWriterReader,
) -> list[ResumeTemplateResponse]:
    """Return the server-authoritative template catalogue."""
    return [
        ResumeTemplateResponse.model_validate(asdict(template)) for template in RESUME_TEMPLATES
    ]


@router.get("/sources", response_model=list[ResumeSourceResponse])
async def list_resume_sources(
    account: ResumeWriterReader,
    database: DatabaseDependency,
    query: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[ResumeSourceResponse]:
    async with database.tenant_connection(account.tenant_id) as connection:
        rows = await repository.list_sources(
            connection,
            tenant_id=account.tenant_id,
            query=query,
            limit=limit,
        )
    return [ResumeSourceResponse.model_validate(row) for row in rows]


@router.get("/documents", response_model=list[ResumeDocumentResponse])
async def list_resume_documents(
    account: ResumeWriterReader,
    database: DatabaseDependency,
) -> list[ResumeDocumentResponse]:
    async with database.tenant_connection(account.tenant_id) as connection:
        rows = await repository.list_documents(connection, tenant_id=account.tenant_id)
    return [ResumeDocumentResponse.model_validate(row) for row in rows]


@router.post(
    "/documents",
    response_model=ResumeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resume_document(
    payload: ResumeDocumentCreate,
    account: ResumeWriterEditor,
    database: DatabaseDependency,
) -> ResumeDocumentResponse:
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.create_document(
            connection,
            tenant_id=account.tenant_id,
            user_id=account.user_id,
            source_profile_id=payload.source_resume_profile_id,
            template_key=payload.template_key,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="未找到可用的简历来源")
    return ResumeDocumentResponse.model_validate(row)


@router.get("/documents/{document_id}", response_model=ResumeDocumentResponse)
async def get_resume_document(
    document_id: UUID,
    account: ResumeWriterReader,
    database: DatabaseDependency,
) -> ResumeDocumentResponse:
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.get_document(
            connection,
            tenant_id=account.tenant_id,
            document_id=document_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="简历草稿不存在")
    return ResumeDocumentResponse.model_validate(row)


@router.put("/documents/{document_id}", response_model=ResumeDocumentResponse)
async def update_resume_document(
    document_id: UUID,
    payload: ResumeDocumentUpdate,
    account: ResumeWriterEditor,
    database: DatabaseDependency,
) -> ResumeDocumentResponse:
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.update_document(
            connection,
            tenant_id=account.tenant_id,
            document_id=document_id,
            update=payload,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="简历草稿不存在")
    return ResumeDocumentResponse.model_validate(row)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume_document(
    document_id: UUID,
    account: ResumeWriterEditor,
    database: DatabaseDependency,
) -> Response:
    """Permanently delete one tenant-owned resume draft."""
    async with database.tenant_connection(account.tenant_id) as connection:
        deleted = await repository.delete_document(
            connection,
            tenant_id=account.tenant_id,
            document_id=document_id,
        )
    if not deleted:
        raise HTTPException(status_code=404, detail="简历草稿不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/documents/{document_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
async def put_resume_photo(
    document_id: UUID,
    request: Request,
    account: ResumeWriterEditor,
    database: DatabaseDependency,
) -> Response:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_RESUME_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="照片大小必须在 5 MiB 以内")
        chunks.append(chunk)
    image_bytes = b"".join(chunks)
    try:
        normalized_media_type, normalized_bytes = normalize_resume_photo(
            media_type,
            image_bytes,
        )
    except UnsafeImageError as error:
        raise HTTPException(
            status_code=422,
            detail="照片无效；仅支持安全的单帧 JPG、PNG 或 WebP",
        ) from error
    async with database.tenant_connection(account.tenant_id) as connection:
        updated = await repository.put_photo(
            connection,
            tenant_id=account.tenant_id,
            document_id=document_id,
            media_type=normalized_media_type,
            image_bytes=normalized_bytes,
        )
    if not updated:
        raise HTTPException(status_code=404, detail="简历草稿不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/documents/{document_id}/photo")
async def get_resume_photo(
    document_id: UUID,
    account: ResumeWriterReader,
    database: DatabaseDependency,
) -> Response:
    async with database.tenant_connection(account.tenant_id) as connection:
        photo = await repository.get_photo(
            connection,
            tenant_id=account.tenant_id,
            document_id=document_id,
        )
    if photo is None:
        raise HTTPException(status_code=404, detail="简历照片不存在")
    media_type, image_bytes = photo
    return Response(
        content=image_bytes,
        media_type=media_type,
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/documents/{document_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume_photo(
    document_id: UUID,
    account: ResumeWriterEditor,
    database: DatabaseDependency,
) -> Response:
    async with database.tenant_connection(account.tenant_id) as connection:
        await repository.delete_photo(
            connection,
            tenant_id=account.tenant_id,
            document_id=document_id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/documents/{document_id}/export/{export_format}")
async def export_resume_document(
    document_id: UUID,
    export_format: str,
    account: ResumeWriterReader,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> Response:
    if export_format not in {"html", "pdf"}:
        raise HTTPException(status_code=404, detail="不支持的简历导出格式")
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.get_document(
            connection,
            tenant_id=account.tenant_id,
            document_id=document_id,
        )
        photo = await repository.get_photo(
            connection,
            tenant_id=account.tenant_id,
            document_id=document_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="简历草稿不存在")
    html_text = render_resume_html(
        title=str(row["title"]),
        template_key=str(row["template_key"]),
        theme_color=str(row["theme_color"]),
        content_value=row["content"],
        photo=photo,
    )
    headers = {
        "Content-Disposition": (f'attachment; filename="resume-{document_id}.{export_format}"')
    }
    if export_format == "html":
        return Response(
            content=html_text,
            media_type="text/html; charset=utf-8",
            headers=headers,
        )
    try:
        async with _PDF_EXPORT_LIMIT:
            pdf = await asyncio.to_thread(
                render_resume_pdf,
                html_text,
                browser_path=settings.pdf_browser_path,
            )
    except (RuntimeError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=503, detail="当前环境无法生成 PDF") from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers=headers,
    )
