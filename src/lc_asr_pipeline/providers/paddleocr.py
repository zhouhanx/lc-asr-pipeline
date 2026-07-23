"""Async PaddleOCR official document-parsing API adapter."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from lc_asr_pipeline.schemas.ocr import PaddleOCRResult
from lc_asr_pipeline.services.network_policy import (
    UnsafeProviderURL,
    enforce_provider_network_policy,
)

ProgressCallback = Callable[[int, int], Awaitable[None]]
PADDLEOCR_RESULT_HOST_PATTERN = re.compile(
    r"^paddleocr-store(?:-\d+)?\.bj\.bcebos\.com$"
)


class PaddleOCRProviderError(RuntimeError):
    """Raised when PaddleOCR returns a failed or malformed job."""


class PaddleOCRProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        request_timeout_seconds: float = 120.0,
        poll_timeout_seconds: float = 1800.0,
        poll_interval_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        root = base_url.rstrip("/")
        self._jobs_url = root if root.endswith("/jobs") else f"{root}/jobs"
        self._api_key = api_key
        self._model = model
        self._request_timeout = request_timeout_seconds
        self._poll_timeout = poll_timeout_seconds
        self._poll_interval = poll_interval_seconds
        self._transport = transport

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"bearer {self._api_key}"}

    async def parse_document(
        self,
        file_path: Path,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> PaddleOCRResult:
        await enforce_provider_network_policy(
            self._jobs_url,
            trusted_hosts={"paddleocr.aistudio-app.com"},
        )
        form = {
            "model": self._model,
            "optionalPayload": json.dumps(
                {
                    "useDocOrientationClassify": False,
                    "useDocUnwarping": False,
                    "useChartRecognition": False,
                }
            ),
        }
        async with httpx.AsyncClient(
            timeout=self._request_timeout,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            with file_path.open("rb") as source:
                response = await client.post(
                    self._jobs_url,
                    headers=self._headers,
                    data=form,
                    files={
                        "file": (
                            file_path.name,
                            source,
                            "application/octet-stream",
                        )
                    },
                )
            response.raise_for_status()
            try:
                job_id = str(response.json()["data"]["jobId"])
            except (KeyError, TypeError, ValueError) as exc:
                raise PaddleOCRProviderError(
                    "PaddleOCR returned an invalid submission response"
                ) from exc

            deadline = asyncio.get_running_loop().time() + self._poll_timeout
            result_url = ""
            status_payload: dict[str, Any] = {}
            while asyncio.get_running_loop().time() < deadline:
                status_response = await client.get(
                    f"{self._jobs_url}/{job_id}",
                    headers=self._headers,
                )
                status_response.raise_for_status()
                try:
                    status_payload = status_response.json()["data"]
                    state = str(status_payload["state"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise PaddleOCRProviderError(
                        "PaddleOCR returned an invalid status response"
                    ) from exc
                progress = status_payload.get("extractProgress") or {}
                total = int(progress.get("totalPages") or 0)
                extracted = int(progress.get("extractedPages") or 0)
                if progress_callback is not None and total > 0:
                    await progress_callback(extracted, total)
                if state == "done":
                    result_url = str((status_payload.get("resultUrl") or {}).get("jsonUrl") or "")
                    break
                if state == "failed":
                    raise PaddleOCRProviderError("PaddleOCR document parsing failed")
                if state not in {"pending", "running"}:
                    raise PaddleOCRProviderError("PaddleOCR returned an unknown job state")
                await asyncio.sleep(self._poll_interval)
            else:
                raise PaddleOCRProviderError("PaddleOCR polling timed out")

            if not result_url:
                raise PaddleOCRProviderError("PaddleOCR result URL is missing")
            result_host = (urlsplit(result_url).hostname or "").casefold().rstrip(".")
            if not PADDLEOCR_RESULT_HOST_PATTERN.fullmatch(result_host):
                raise PaddleOCRProviderError(
                    f"PaddleOCR result host is not allowed: {result_host or 'unknown'}"
                )
            try:
                await enforce_provider_network_policy(
                    result_url,
                    trusted_hosts={result_host},
                )
            except UnsafeProviderURL as exc:
                raise PaddleOCRProviderError(
                    f"PaddleOCR result host is not allowed: {result_host}"
                ) from exc
            result_response = await client.get(result_url)
            result_response.raise_for_status()

        pages: list[str] = []
        for line in result_response.text.splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PaddleOCRProviderError("PaddleOCR result contains invalid JSONL") from exc
            result = payload.get("result") or {}
            layouts = result.get("layoutParsingResults") or []
            for layout in layouts:
                markdown = layout.get("markdown") or {}
                text = markdown.get("text") or layout.get("markdownText") or ""
                if isinstance(text, str) and text.strip():
                    pages.append(text.strip())
        page_count = len(pages)
        if page_count == 0:
            raise PaddleOCRProviderError("PaddleOCR returned no Markdown pages")
        return PaddleOCRResult(
            provider_job_id=job_id,
            markdown_text="\n\n---\n\n".join(pages),
            page_count=page_count,
            raw_result={
                "job_id": job_id,
                "state": status_payload.get("state"),
                "extract_progress": status_payload.get("extractProgress") or {},
                "markdown_text": "\n\n---\n\n".join(pages),
            },
        )
