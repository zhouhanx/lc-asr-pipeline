"""OpenAI-compatible audio transcription provider."""

from __future__ import annotations

from typing import Any

import httpx

from lc_asr_pipeline.schemas.transcription import TranscriptionRequest, TranscriptionResult


class OpenAICompatibleASRProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 3600.0,
        transport: httpx.BaseTransport | None = None,
        async_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport
        self.async_transport = async_transport

    def _form(self, request: TranscriptionRequest) -> dict[str, str]:
        data = {
            "model": self.model,
            "response_format": "verbose_json",
            "prompt": request.prompt,
            "timestamps": str(request.timestamps).lower(),
            "diarize": str(request.diarize).lower(),
            "min_speakers": str(request.min_speakers),
            "max_speakers": str(request.max_speakers),
        }
        if request.language:
            data["language"] = request.language
        if request.num_speakers is not None:
            data["num_speakers"] = str(request.num_speakers)
        return data

    def endpoint(self, path: str) -> str:
        if self.base_url.endswith("/v1") and path.startswith("/v1/"):
            return self.base_url + path[3:]
        return self.base_url + path

    def _result(self, payload: dict[str, Any]) -> TranscriptionResult:
        return TranscriptionResult.model_validate(
            {**payload, "provider": self.name, "model": self.model}
        )

    def invoke(self, request: TranscriptionRequest) -> TranscriptionResult:
        with request.audio_path.open("rb") as audio, httpx.Client(
            timeout=self.timeout, transport=self.transport
        ) as client:
            response = client.post(
                self.endpoint("/v1/audio/transcriptions"),
                headers={"Authorization": f"Bearer {self.api_key}"},
                data=self._form(request),
                files={"file": (request.audio_path.name, audio)},
            )
        response.raise_for_status()
        return self._result(response.json())

    async def ainvoke(self, request: TranscriptionRequest) -> TranscriptionResult:
        with request.audio_path.open("rb") as audio:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self.async_transport
            ) as client:
                response = await client.post(
                    self.endpoint("/v1/audio/transcriptions"),
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data=self._form(request),
                    files={"file": (request.audio_path.name, audio)},
                )
        response.raise_for_status()
        return self._result(response.json())
