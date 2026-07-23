"""Speaker-aware transcript refinement contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from lc_asr_pipeline.schemas.transcription import TranscriptSegment

SpeakerMode = Literal["single", "double", "multiple"]


class TranscriptRefinementRequest(BaseModel):
    raw_text: str = Field(min_length=1)
    speaker_mode: SpeakerMode
    speaker_hints: list[TranscriptSegment] = Field(default_factory=list)


class RefinedUtterance(BaseModel):
    speaker: str = Field(pattern=r"^用户[1-9][0-9]*$")
    text: str = Field(min_length=1)


class TranscriptRefinementResult(BaseModel):
    formatted_text: str = Field(min_length=1)
    utterances: list[RefinedUtterance] = Field(min_length=1)
    model: str
