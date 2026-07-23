"""ASR provider protocol."""

from typing import Protocol

from lc_asr_pipeline.schemas.transcription import TranscriptionRequest, TranscriptionResult


class ASRProvider(Protocol):
    def invoke(self, request: TranscriptionRequest) -> TranscriptionResult: ...

    async def ainvoke(self, request: TranscriptionRequest) -> TranscriptionResult: ...

