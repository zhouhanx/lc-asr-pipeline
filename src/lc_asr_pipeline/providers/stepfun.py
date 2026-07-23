"""StepFun StepAudio SSE transcription provider."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx

from lc_asr_pipeline.schemas.transcription import (
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegment,
)

SUPPORTED_SUFFIXES = {".mp3", ".ogg", ".wav"}


class StepFunASRProvider:
    """Adapt local audio files to StepFun's official HTTP+SSE ASR API."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str = "stepaudio-2.5-asr",
        timeout_seconds: float = 3600.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    def endpoint(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/audio/asr/sse"
        return f"{self.base_url}/v1/audio/asr/sse"

    @contextmanager
    def _supported_audio(self, source: Path) -> Iterator[Path]:
        if source.suffix.lower() in SUPPORTED_SUFFIXES:
            yield source
            return
        descriptor, temporary_name = tempfile.mkstemp(prefix="lc_asr_stepfun_", suffix=".mp3")
        os.close(descriptor)
        Path(temporary_name).unlink(missing_ok=True)
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(source),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-b:a",
                    "64k",
                    temporary_name,
                ],
                check=True,
            )
            yield Path(temporary_name)
        finally:
            Path(temporary_name).unlink(missing_ok=True)

    @staticmethod
    def _language(value: str | None) -> str:
        if not value:
            return "zh"
        return "zh" if value.lower() in {"chinese", "中文", "zh-cn"} else value

    def _payload(self, audio: Path, request: TranscriptionRequest) -> dict[str, Any]:
        return {
            "audio": {
                "data": base64.b64encode(audio.read_bytes()).decode("ascii"),
                "input": {
                    "transcription": {
                        "language": self._language(request.language),
                        "hotwords": [],
                        "model": self.model,
                        "enable_itn": True,
                        "enable_timestamp": request.timestamps,
                    },
                    "format": {"type": audio.suffix.lower().removeprefix(".")},
                },
            }
        }

    def _result(self, response: httpx.Response) -> TranscriptionResult:
        text = ""
        segments: list[TranscriptSegment] = []
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line.removeprefix("data:").strip()
            if not raw or raw == "[DONE]":
                continue
            event = json.loads(raw)
            event_type = event.get("type")
            if event_type == "error":
                raise RuntimeError("StepFun ASR returned an error event")
            if event_type == "transcript.text.delta":
                delta = str(event.get("delta") or "")
                start = float(event.get("start_time") or 0) / 1000
                end = float(event.get("end_time") or 0) / 1000
                if delta and end >= start:
                    segments.append(TranscriptSegment(text=delta, start=start, end=end))
            elif event_type == "transcript.text.done":
                text = str(event.get("text") or "")
        if not text:
            text = "".join(segment.text for segment in segments)
        if not text:
            raise RuntimeError("StepFun ASR returned no transcript")
        return TranscriptionResult(
            text=text,
            language="zh",
            segments=segments,
            provider=self.name,
            model=self.model,
        )

    def invoke(self, request: TranscriptionRequest) -> TranscriptionResult:
        if request.diarize:
            raise ValueError("StepFun SSE provider does not support speaker diarization")
        with self._supported_audio(request.audio_path) as audio, httpx.Client(
            timeout=self.timeout,
            transport=self.transport,
        ) as client, client.stream(
            "POST",
            self.endpoint(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
            },
            json=self._payload(audio, request),
        ) as response:
            response.raise_for_status()
            return self._result(response)

    async def ainvoke(self, request: TranscriptionRequest) -> TranscriptionResult:
        return await asyncio.to_thread(self.invoke, request)
