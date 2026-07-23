"""DeepSeek transcript cleanup behind a typed LangChain Runnable."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field, ValidationError

from lc_asr_pipeline.schemas.refinement import (
    RefinedUtterance,
    SpeakerMode,
    TranscriptRefinementRequest,
    TranscriptRefinementResult,
)


class DeepSeekRefinementError(RuntimeError):
    """Raised when DeepSeek does not return a usable structured transcript."""


class _DeepSeekPayload(BaseModel):
    utterances: list[RefinedUtterance] = Field(min_length=1)


_MODE_INSTRUCTIONS: dict[SpeakerMode, str] = {
    "single": "这是单人录音。所有内容都标记为用户1，不要创建其他用户。",
    "double": "这是双人对话。根据语义、问答关系和说话人提示拆分为用户1和用户2。",
    "multiple": "这是多人对话。按首次出现顺序标记为用户1、用户2、用户3……。",
}


class DeepSeekTranscriptRefiner:
    """Call the official OpenAI-compatible DeepSeek chat-completion API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        provider_type: str = "deepseek",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self._provider_type = provider_type
        self._transport = transport

    def invoke(self, request: TranscriptRefinementRequest) -> TranscriptRefinementResult:
        return asyncio.run(self.ainvoke(request))

    async def ainvoke(
        self, request: TranscriptRefinementRequest
    ) -> TranscriptRefinementResult:
        hint_text = "\n".join(
            f"{segment.speaker or 'UNKNOWN'}: {segment.text}"
            for segment in request.speaker_hints
            if segment.text.strip()
        )
        system_prompt = (
            "你是中文语音转写校对员。必须完整保留原意和信息顺序，不得总结、删减或补充事实。"
            "根据指定人数恢复说话人轮次；结合上下文修正明确的同音错字、关键词、产品名、"
            "公司名、英文缩写和专业术语。无法确定时保留原文。"
            "只输出 JSON，格式为 {\"utterances\":[{\"speaker\":\"用户1\","
            "\"text\":\"完整话语\"}]}。speaker 只能使用用户加正整数。"
        )
        user_prompt = (
            f"人数模式：{request.speaker_mode}\n"
            f"规则：{_MODE_INSTRUCTIONS[request.speaker_mode]}\n"
            f"ASR 原始文本：\n{request.raw_text}\n"
        )
        if hint_text:
            user_prompt += f"\nASR/声纹提供的说话人提示（仅作辅助）：\n{hint_text}"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "max_tokens": 65536,
        }
        if self._provider_type == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise DeepSeekRefinementError("DeepSeek returned empty content")
            parsed = _DeepSeekPayload.model_validate_json(content)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise DeepSeekRefinementError("DeepSeek returned invalid structured output") from exc

        allowed_max = (
            1
            if request.speaker_mode == "single"
            else 2
            if request.speaker_mode == "double"
            else 99
        )
        normalized: list[RefinedUtterance] = []
        for utterance in parsed.utterances:
            speaker_number = int(utterance.speaker.removeprefix("用户"))
            if speaker_number > allowed_max:
                raise DeepSeekRefinementError(
                    "DeepSeek returned a speaker outside the selected mode"
                )
            normalized.append(
                RefinedUtterance(speaker=utterance.speaker, text=utterance.text.strip())
            )
        formatted = "\n".join(
            f"{utterance.speaker}：{utterance.text}" for utterance in normalized
        )
        return TranscriptRefinementResult(
            formatted_text=formatted,
            utterances=normalized,
            model=self._model,
        )


def build_transcript_refinement_chain(
    refiner: DeepSeekTranscriptRefiner,
) -> Runnable[TranscriptRefinementRequest, TranscriptRefinementResult]:
    """Expose DeepSeek refinement as the application's typed LangChain boundary."""
    return RunnableLambda(refiner.invoke, afunc=refiner.ainvoke).with_types(
        input_type=TranscriptRefinementRequest,
        output_type=TranscriptRefinementResult,
    )
