"""Provider-neutral transcription contracts."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class TranscriptionRequest(BaseModel):
    audio_path: Path
    language: str | None = None
    prompt: str = Field(default="", max_length=4000)
    timestamps: bool = True
    diarize: bool = False
    num_speakers: int | None = Field(default=None, ge=1, le=32)
    min_speakers: int = Field(default=1, ge=1, le=32)
    max_speakers: int = Field(default=8, ge=1, le=32)


class TranscriptSegment(BaseModel):
    text: str = ""
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    speaker: str | None = None


class TranscriptionResult(BaseModel):
    text: str
    language: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)
    speaker_segments: list[TranscriptSegment] = Field(default_factory=list)
    provider: str
    model: str

