"""Transcription job endpoints."""

import html
import re
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, Security, status

from lc_asr_pipeline.api.dependencies import DatabaseDependency, SettingsDependency
from lc_asr_pipeline.api.security import CurrentAccount, get_current_account
from lc_asr_pipeline.repositories.identity import Account
from lc_asr_pipeline.repositories.jobs import JobRepository
from lc_asr_pipeline.repositories.uploads import UploadRepository
from lc_asr_pipeline.schemas.job import (
    PublicTranscriptionJobDetail,
    PublicTranscriptionJobResponse,
    TranscriptionJobCreate,
    TranscriptionJobDeleteResponse,
    TranscriptionJobDetail,
    TranscriptionJobResponse,
    TranscriptionJobVisibilityUpdate,
)
from lc_asr_pipeline.services.storage import process_pending_storage_deletions

router = APIRouter(prefix="/jobs", tags=["jobs"])
repository = JobRepository()
upload_repository = UploadRepository()
JobReader = Annotated[Account, Security(get_current_account, scopes=["jobs:read"])]
JobWriter = Annotated[Account, Security(get_current_account, scopes=["jobs:write"])]
_DIALOGUE_LINE = re.compile(r"^(用户(?P<number>[1-9][0-9]*))[：:]\s*(?P<text>.*)$")


@router.get("", response_model=list[TranscriptionJobResponse])
async def list_jobs(
    account: JobReader,
    database: DatabaseDependency,
) -> list[TranscriptionJobResponse]:
    async with database.tenant_connection(account.tenant_id) as connection:
        rows = await repository.list_for_tenant(connection, tenant_id=account.tenant_id)
    return [TranscriptionJobResponse.model_validate(row) for row in rows]


@router.get("/public", response_model=list[PublicTranscriptionJobResponse])
async def list_public_jobs(
    _: CurrentAccount,
    database: DatabaseDependency,
) -> list[PublicTranscriptionJobResponse]:
    async with database.system_connection() as connection:
        rows = await repository.list_public(connection)
    return [PublicTranscriptionJobResponse.model_validate(row) for row in rows]


@router.get("/public/{job_id}", response_model=PublicTranscriptionJobDetail)
async def public_job_detail(
    job_id: UUID,
    _: CurrentAccount,
    database: DatabaseDependency,
    include_segments: bool = True,
) -> PublicTranscriptionJobDetail:
    async with database.system_connection() as connection:
        row = await repository.get_public(connection, job_id=job_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Public transcription job not found")
        segments = (
            await repository.segments_for_public_job(connection, job_id=job_id)
            if include_segments
            else []
        )
    return PublicTranscriptionJobDetail.model_validate({**row, "segments": segments})


@router.get("/public/{job_id}/export/{export_format}")
async def export_public_job(
    job_id: UUID,
    export_format: str,
    _: CurrentAccount,
    database: DatabaseDependency,
) -> Response:
    _validate_export_format(export_format)
    async with database.system_connection() as connection:
        row = await repository.get_public(connection, job_id=job_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Public transcription job not found")
        _validate_completed_transcript(row)
        segments = await repository.segments_for_public_job(connection, job_id=job_id)
    detail = PublicTranscriptionJobDetail.model_validate({**row, "segments": segments})
    return build_job_export_response(
        job_id=job_id,
        export_format=export_format,
        row=row,
        segments=segments,
        json_payload=detail.model_dump_json(indent=2),
    )


@router.patch("/{job_id}/visibility", response_model=TranscriptionJobResponse)
async def update_job_visibility(
    job_id: UUID,
    payload: TranscriptionJobVisibilityUpdate,
    account: JobWriter,
    database: DatabaseDependency,
) -> TranscriptionJobResponse:
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.update_visibility(
            connection,
            tenant_id=account.tenant_id,
            job_id=job_id,
            visibility=payload.visibility,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Transcription job not found")
    return TranscriptionJobResponse.model_validate(row)


@router.get("/{job_id}", response_model=TranscriptionJobDetail)
async def job_detail(
    job_id: UUID,
    account: JobReader,
    database: DatabaseDependency,
    include_segments: bool = True,
) -> TranscriptionJobDetail:
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.get_for_tenant(
            connection, tenant_id=account.tenant_id, job_id=job_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Transcription job not found")
        segments = (
            await repository.segments_for_job(
                connection, tenant_id=account.tenant_id, job_id=job_id
            )
            if include_segments
            else []
        )
    return TranscriptionJobDetail.model_validate({**row, "segments": segments})


def _subtitle_time(seconds: float, *, vtt: bool) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    separator = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def _dialogue_html(title: str, transcript: str) -> str:
    messages: list[str] = []
    for line in transcript.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _DIALOGUE_LINE.match(stripped)
        if match:
            speaker = match.group(1)
            text = match.group("text")
            side = "right" if int(match.group("number")) % 2 == 0 else "left"
        else:
            speaker, text, side = "转写", stripped, "left"
        messages.append(
            f'<article class="message {side}"><div class="speaker">'
            f'{html.escape(speaker)}</div><div class="bubble">'
            f"{html.escape(text)}</div></article>"
        )
    safe_title = html.escape(title)
    body = "\n".join(messages) or '<p class="empty">暂无转写文本</p>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title} · LC</title>
<style>
:root {{ --paper:#fff8e8; --ink:#171717; --yellow:#ffd84d; --mint:#93efba; }}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
  background-image:linear-gradient(#17171712 1px,transparent 1px),
    linear-gradient(90deg,#17171712 1px,transparent 1px);
  background-size:24px 24px;
}}
main {{ width:min(920px,calc(100% - 32px)); margin:32px auto 64px; }}
header {{
  border:4px solid var(--ink); background:#fff; padding:24px;
  box-shadow:8px 8px 0 var(--ink); margin-bottom:36px;
}}
h1 {{ margin:0 0 8px; font-size:clamp(24px,5vw,40px); overflow-wrap:anywhere; }}
.brand {{
  display:inline-block; border:2px solid var(--ink); background:var(--yellow);
  padding:5px 9px; font-weight:900; margin-bottom:16px;
}}
.conversation {{ display:flex; flex-direction:column; gap:18px; }}
.message {{ display:flex; flex-direction:column; width:min(78%,680px); }}
.message.right {{ align-self:flex-end; align-items:flex-end; }}
.speaker {{ font-weight:900; margin:0 8px 6px; }}
.bubble {{
  border:3px solid var(--ink); background:#fff; padding:15px 18px;
  line-height:1.8; box-shadow:5px 5px 0 var(--ink);
  white-space:pre-wrap; overflow-wrap:anywhere;
}}
.right .bubble {{ background:var(--mint); box-shadow:-5px 5px 0 var(--ink); }}
.empty {{ text-align:center; border:3px dashed var(--ink); padding:40px; }}
@media(max-width:600px) {{ .message {{ width:92%; }} header {{ padding:18px; }} }}
</style>
</head>
<body><main><header><span class="brand">LC</span><h1>{safe_title}</h1>
<p>对话转写记录</p></header><section class="conversation">{body}</section></main></body>
</html>"""


@router.get("/{job_id}/export/{export_format}")
async def export_job(
    job_id: UUID,
    export_format: str,
    account: JobReader,
    database: DatabaseDependency,
) -> Response:
    _validate_export_format(export_format)
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.get_for_tenant(
            connection, tenant_id=account.tenant_id, job_id=job_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Transcription job not found")
        _validate_completed_transcript(row)
        segments = await repository.segments_for_job(
            connection, tenant_id=account.tenant_id, job_id=job_id
        )
    detail = TranscriptionJobDetail.model_validate({**row, "segments": segments})
    return build_job_export_response(
        job_id=job_id,
        export_format=export_format,
        row=row,
        segments=segments,
        json_payload=detail.model_dump_json(indent=2),
    )


def _validate_export_format(export_format: str) -> None:
    if export_format not in {"txt", "json", "srt", "vtt", "html"}:
        raise HTTPException(status_code=404, detail="Export format not found")


def _validate_completed_transcript(row: dict[str, object]) -> None:
    if row["status"] != "completed" or row["transcript_text"] is None:
        raise HTTPException(status_code=409, detail="Transcript is not complete")


def build_job_export_response(
    *,
    job_id: UUID,
    export_format: str,
    row: dict[str, object],
    segments: list[dict[str, object]],
    json_payload: str,
) -> Response:
    filename = f"transcript-{job_id}.{export_format}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if export_format == "txt":
        return Response(str(row["transcript_text"]), media_type="text/plain", headers=headers)
    if export_format == "json":
        return Response(
            json_payload,
            media_type="application/json",
            headers=headers,
        )
    if export_format == "html":
        return Response(
            _dialogue_html(str(row["source_path"]).split("/")[-1], str(row["transcript_text"])),
            media_type="text/html; charset=utf-8",
            headers=headers,
        )
    vtt = export_format == "vtt"
    blocks = ["WEBVTT\n"] if vtt else []
    for index, segment in enumerate(segments, start=1):
        start_seconds = segment["start_seconds"]
        end_seconds = segment["end_seconds"]
        if not isinstance(start_seconds, (int, float, Decimal)) or not isinstance(
            end_seconds, (int, float, Decimal)
        ):
            raise ValueError("Transcript segment timestamps must be numeric")
        label = f"{segment['speaker']}: " if segment["speaker"] else ""
        blocks.append(
            f"{index}\n{_subtitle_time(float(start_seconds), vtt=vtt)} --> "
            f"{_subtitle_time(float(end_seconds), vtt=vtt)}\n"
            f"{label}{segment['text']}\n"
        )
    media_type = "text/vtt" if vtt else "application/x-subrip"
    return Response("\n".join(blocks), media_type=media_type, headers=headers)


@router.post("/{job_id}/cancel", response_model=TranscriptionJobResponse)
async def cancel_job(
    job_id: UUID,
    account: JobWriter,
    database: DatabaseDependency,
) -> TranscriptionJobResponse:
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.request_cancel(
            connection, tenant_id=account.tenant_id, job_id=job_id
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Transcription job not found")
    return TranscriptionJobResponse.model_validate(row)


@router.post("/{job_id}/retry", response_model=TranscriptionJobResponse)
async def retry_job(
    job_id: UUID,
    account: JobWriter,
    database: DatabaseDependency,
) -> TranscriptionJobResponse:
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.retry(connection, tenant_id=account.tenant_id, job_id=job_id)
    if row is None:
        raise HTTPException(status_code=409, detail="Job cannot be retried")
    return TranscriptionJobResponse.model_validate(row)


@router.delete("/{job_id}", response_model=TranscriptionJobDeleteResponse)
async def delete_job(
    job_id: UUID,
    account: JobWriter,
    database: DatabaseDependency,
    settings: SettingsDependency,
) -> TranscriptionJobDeleteResponse:
    file_result = None
    async with database.tenant_connection(account.tenant_id) as connection:
        row = await repository.delete_for_tenant(
            connection, tenant_id=account.tenant_id, job_id=job_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Transcription job not found")
        if row["blocked"]:
            raise HTTPException(
                status_code=409,
                detail="任务正在运行，请先取消或等待完成后再删除。",
            )
        if row["remaining_jobs"] == 0:
            file_result = await upload_repository.delete_file_for_tenant(
                connection,
                tenant_id=account.tenant_id,
                file_id=row["uploaded_file_id"],
                deletion_reason="job_delete",
            )
    if file_result is not None and not file_result["blocked"]:
        await process_pending_storage_deletions(
            database,
            data_path=settings.data_path,
            limit=1,
            deletion_ids=[int(file_result["deletion_id"])],
        )
    deleted_files = 0 if file_result is None else int(file_result["deleted_files"])
    return TranscriptionJobDeleteResponse(
        id=job_id,
        deleted_jobs=1,
        deleted_files=deleted_files,
        source_deleted=deleted_files > 0,
    )


@router.post(
    "",
    response_model=list[TranscriptionJobResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_jobs(
    payload: TranscriptionJobCreate,
    account: JobWriter,
    database: DatabaseDependency,
) -> list[TranscriptionJobResponse]:
    if len(payload.uploaded_file_ids) != len(set(payload.uploaded_file_ids)):
        raise HTTPException(status_code=422, detail="uploaded_file_ids must be unique")
    async with database.tenant_connection(account.tenant_id) as connection:
        rows = await repository.create_many(
            connection,
            tenant_id=account.tenant_id,
            user_id=account.user_id,
            provider_id=payload.provider_id,
            text_provider_id=payload.text_provider_id,
            file_ids=payload.uploaded_file_ids,
            language=payload.language,
            diarize=payload.diarize,
            speaker_mode=payload.speaker_mode,
        )
    if len(rows) != len(payload.uploaded_file_ids):
        raise HTTPException(
            status_code=409,
            detail="Provider unavailable, file not ready, or job already exists",
        )
    return [TranscriptionJobResponse.model_validate(row) for row in rows]
