"""Tenant-scoped resumable upload endpoints."""

from __future__ import annotations

import hashlib
import hmac
import os
import shutil
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Security, status

from lc_asr_pipeline.api.dependencies import DatabaseDependency, SettingsDependency
from lc_asr_pipeline.api.security import get_current_account
from lc_asr_pipeline.repositories.identity import Account
from lc_asr_pipeline.repositories.uploads import UploadRepository
from lc_asr_pipeline.schemas.upload import (
    HistoricalFileDeleteResponse,
    HistoricalFileResponse,
    UploadBatchCreate,
    UploadBatchResponse,
    UploadCancelResponse,
    UploadCompleteResponse,
    UploadFileResponse,
    UploadProgressResponse,
)
from lc_asr_pipeline.services.archive import extract_audio_archive
from lc_asr_pipeline.services.storage import delete_uploaded_file_storage

router = APIRouter(prefix="/uploads", tags=["uploads"])
repository = UploadRepository()
UploadWriter = Annotated[Account, Security(get_current_account, scopes=["jobs:write"])]
UploadReader = Annotated[Account, Security(get_current_account, scopes=["jobs:read"])]


def _file_root(data_path: Path, tenant_id: UUID, file_id: UUID) -> Path:
    return data_path.resolve() / "uploads" / str(tenant_id) / str(file_id)


def _validate_file_signature(path: Path, file_kind: str) -> None:
    if file_kind == "audio":
        return
    with path.open("rb") as source:
        header = source.read(16)
    if file_kind == "pdf":
        valid = header.startswith(b"%PDF-")
    else:
        valid = (
            header.startswith(b"\x89PNG\r\n\x1a\n")
            or header.startswith(b"\xff\xd8\xff")
            or header.startswith(b"BM")
            or header.startswith((b"II*\x00", b"MM\x00*"))
            or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
        )
    if not valid:
        raise HTTPException(
            status_code=422,
            detail=f"Uploaded {file_kind} file signature is invalid",
        )


@router.get("/history", response_model=list[HistoricalFileResponse])
async def upload_history(
    account: UploadReader,
    database: DatabaseDependency,
    file_kind: Literal["audio", "image", "pdf"] | None = None,
) -> list[HistoricalFileResponse]:
    async with database.connection() as connection:
        rows = await repository.list_history(
            connection,
            tenant_id=account.tenant_id,
            file_kind=file_kind,
        )
    return [HistoricalFileResponse.model_validate(row) for row in rows]


@router.delete(
    "/history/{file_id}",
    response_model=HistoricalFileDeleteResponse,
)
async def delete_historical_file(
    file_id: UUID,
    account: UploadWriter,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> HistoricalFileDeleteResponse:
    async with database.connection() as connection:
        result = await repository.delete_file_for_tenant(
            connection, tenant_id=account.tenant_id, file_id=file_id
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Historical file not found")
        if result["blocked"]:
            raise HTTPException(
                status_code=409,
                detail="文件存在运行中的任务，请先取消或等待完成后再删除。",
            )
    delete_uploaded_file_storage(
        data_path=settings.data_path,
        tenant_id=account.tenant_id,
        root_file_id=result["root_file_id"],
        exact_storage_path=result["exact_storage_path"],
    )
    return HistoricalFileDeleteResponse(
        id=file_id,
        deleted_jobs=result["deleted_jobs"],
        deleted_files=result["deleted_files"],
    )


@router.post(
    "/batches",
    response_model=UploadBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_batch(
    payload: UploadBatchCreate,
    account: UploadWriter,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> UploadBatchResponse:
    total_bytes = sum(item.size_bytes for item in payload.files)
    if total_bytes > settings.upload_batch_max_bytes:
        raise HTTPException(status_code=413, detail="Upload batch exceeds 5 GiB")
    async with database.connection() as connection:
        batch, files = await repository.create_batch(
            connection,
            tenant_id=account.tenant_id,
            user_id=account.user_id,
            payload=payload,
            chunk_size=settings.upload_chunk_bytes,
        )
    return UploadBatchResponse(
        **batch,
        files=[UploadFileResponse(**item) for item in files],
    )


@router.post("/batches/{batch_id}/cancel", response_model=UploadCancelResponse)
async def cancel_batch(
    batch_id: UUID,
    account: UploadWriter,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> UploadCancelResponse:
    async with database.connection() as connection:
        file_ids = await repository.cancel_batch(
            connection,
            tenant_id=account.tenant_id,
            batch_id=batch_id,
        )
    if file_ids is None:
        raise HTTPException(status_code=409, detail="Upload batch cannot be cancelled")
    for file_id in file_ids:
        target = _file_root(settings.data_path, account.tenant_id, file_id)
        shutil.rmtree(target, ignore_errors=True)
    return UploadCancelResponse(
        id=batch_id,
        status="cancelled",
        deleted_files=len(file_ids),
    )


@router.get("/files/{file_id}", response_model=UploadProgressResponse)
async def upload_progress(
    file_id: UUID,
    account: UploadWriter,
    database: DatabaseDependency,
) -> UploadProgressResponse:
    async with database.connection() as connection:
        item = await repository.get_file_for_update(
            connection, tenant_id=account.tenant_id, file_id=file_id
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Upload file not found")
        chunks = await repository.chunk_rows(connection, file_id=file_id)
    return UploadProgressResponse(
        file_id=file_id,
        status=str(item["status"]),
        expected_chunks=int(item["expected_chunks"]),
        received_chunks=[int(chunk["chunk_index"]) for chunk in chunks],
    )


@router.put(
    "/files/{file_id}/chunks/{chunk_index}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def upload_chunk(
    file_id: UUID,
    chunk_index: int,
    request: Request,
    account: UploadWriter,
    database: DatabaseDependency,
    settings: SettingsDependency,
    x_chunk_sha256: Annotated[str, Header(pattern=r"^[a-fA-F0-9]{64}$")],
) -> None:
    async with database.connection() as connection:
        item = await repository.get_file_for_update(
            connection, tenant_id=account.tenant_id, file_id=file_id
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Upload file not found")
        expected_chunks = int(item["expected_chunks"])
        if chunk_index < 0 or chunk_index >= expected_chunks:
            raise HTTPException(status_code=416, detail="Chunk index is outside the file range")
        chunks = await repository.chunk_rows(connection, file_id=file_id)
        existing = next(
            (chunk for chunk in chunks if chunk["chunk_index"] == chunk_index),
            None,
        )
        if existing:
            if hmac.compare_digest(str(existing["sha256"]), x_chunk_sha256.lower()):
                return
            raise HTTPException(status_code=409, detail="Chunk checksum conflicts")

        root = _file_root(settings.data_path, account.tenant_id, file_id)
        chunk_dir = root / "chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        final_path = chunk_dir / f"{chunk_index:08d}.part"
        temporary_path = chunk_dir / f".{chunk_index:08d}.{os.getpid()}.tmp"
        digest = hashlib.sha256()
        written = 0
        try:
            with temporary_path.open("xb") as target:
                async for content in request.stream():
                    written += len(content)
                    if written > int(item["chunk_size"]):
                        raise HTTPException(status_code=413, detail="Chunk is too large")
                    digest.update(content)
                    target.write(content)
            expected_size = min(
                int(item["chunk_size"]),
                int(item["size_bytes"]) - chunk_index * int(item["chunk_size"]),
            )
            if written != expected_size or not hmac.compare_digest(
                digest.hexdigest(), x_chunk_sha256.lower()
            ):
                raise HTTPException(status_code=422, detail="Chunk size or checksum mismatch")
            os.replace(temporary_path, final_path)
            await connection.execute(
                """
                INSERT INTO upload_chunks
                    (file_id, chunk_index, offset_bytes, size_bytes, sha256, storage_path)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    file_id,
                    chunk_index,
                    chunk_index * int(item["chunk_size"]),
                    written,
                    digest.hexdigest(),
                    str(final_path),
                ),
            )
            await connection.execute(
                """
                UPDATE uploaded_files SET received_chunks = received_chunks + 1,
                    updated_at = now() WHERE id = %s
                """,
                (file_id,),
            )
            await connection.execute(
                """
                UPDATE upload_batches SET received_bytes = received_bytes + %s,
                    updated_at = now() WHERE id = %s
                """,
                (written, item["batch_id"]),
            )
        finally:
            temporary_path.unlink(missing_ok=True)


@router.post("/files/{file_id}/complete", response_model=UploadCompleteResponse)
async def complete_upload(
    file_id: UUID,
    account: UploadWriter,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> UploadCompleteResponse:
    async with database.connection() as connection:
        item = await repository.get_file_for_update(
            connection, tenant_id=account.tenant_id, file_id=file_id
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Upload file not found")
        chunks = await repository.chunk_rows(connection, file_id=file_id)
        expected_chunks = int(item["expected_chunks"])
        indices = [int(chunk["chunk_index"]) for chunk in chunks]
        if indices != list(range(expected_chunks)):
            raise HTTPException(status_code=409, detail="Upload has missing chunks")
        if item["status"] == "ready":
            child_ids = await repository.ready_child_ids(
                connection, parent_file_id=file_id
            )
            return UploadCompleteResponse(
                file_id=file_id,
                status="ready",
                expected_chunks=expected_chunks,
                received_chunks=indices,
                ready_file_ids=child_ids or [file_id],
            )

        root = _file_root(settings.data_path, account.tenant_id, file_id)
        source_dir = root / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(str(item["relative_path"])).suffix
        final_path = source_dir / f"source{suffix}"
        temporary_path = source_dir / ".assembling.tmp"
        digest = hashlib.sha256()
        assembled = 0
        try:
            with temporary_path.open("wb") as target:
                for chunk in chunks:
                    with Path(str(chunk["storage_path"])).open("rb") as source:
                        while content := source.read(8 * 1024 * 1024):
                            assembled += len(content)
                            digest.update(content)
                            target.write(content)
            if assembled != int(item["size_bytes"]):
                raise HTTPException(status_code=422, detail="Assembled file size mismatch")
            expected_sha = item["sha256"]
            if expected_sha and not hmac.compare_digest(str(expected_sha), digest.hexdigest()):
                raise HTTPException(status_code=422, detail="Assembled file checksum mismatch")
            _validate_file_signature(temporary_path, str(item["file_kind"]))
            os.replace(temporary_path, final_path)
            ready_file_ids = [file_id]
            if item["archive_type"]:
                extraction_path = root / f"extracted-{digest.hexdigest()[:16]}"
                try:
                    extracted = extract_audio_archive(
                        final_path,
                        extraction_path,
                        archive_type=str(item["archive_type"]),
                        max_bytes=settings.upload_batch_max_bytes,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                ready_file_ids = await repository.add_extracted_files(
                    connection,
                    parent=item,
                    tenant_id=account.tenant_id,
                    extracted=extracted,
                )
            await connection.execute(
                """
                UPDATE uploaded_files
                SET status = 'ready', storage_path = %s, sha256 = %s, updated_at = now()
                WHERE id = %s
                """,
                (str(final_path), digest.hexdigest(), file_id),
            )
            await connection.execute(
                """
                UPDATE upload_batches b
                SET status = CASE WHEN NOT EXISTS (
                        SELECT 1 FROM uploaded_files f
                        WHERE f.batch_id = b.id AND f.id <> %s AND f.status <> 'ready'
                    ) THEN 'ready' ELSE b.status END,
                    updated_at = now()
                WHERE b.id = %s
                """,
                (file_id, item["batch_id"]),
            )
        finally:
            temporary_path.unlink(missing_ok=True)
    return UploadCompleteResponse(
        file_id=file_id,
        status="ready",
        expected_chunks=expected_chunks,
        received_chunks=indices,
        ready_file_ids=ready_file_ids,
    )
