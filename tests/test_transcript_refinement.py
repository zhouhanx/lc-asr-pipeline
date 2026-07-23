"""DeepSeek transcript-refinement contract tests."""

import json

import httpx
import pytest

from lc_asr_pipeline.schemas.refinement import TranscriptRefinementRequest
from lc_asr_pipeline.schemas.transcription import TranscriptSegment
from lc_asr_pipeline.services.transcript_refinement import (
    DeepSeekRefinementError,
    DeepSeekTranscriptRefiner,
    build_transcript_refinement_chain,
)


@pytest.mark.asyncio
async def test_deepseek_refinement_uses_json_mode_and_formats_two_speakers() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["thinking"] == {"type": "disabled"}
        assert "双人对话" in payload["messages"][1]["content"]
        content = json.dumps(
            {
                "utterances": [
                    {"speaker": "用户1", "text": "请介绍 LangChain 项目。"},
                    {"speaker": "用户2", "text": "它用于编排大模型应用。"},
                ]
            },
            ensure_ascii=False,
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    refiner = DeepSeekTranscriptRefiner(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout_seconds=10,
        transport=httpx.MockTransport(handler),
    )
    result = await build_transcript_refinement_chain(refiner).ainvoke(
        TranscriptRefinementRequest(
            raw_text="请介绍 lang chain 项目 它用于编排大模型应用",
            speaker_mode="double",
            speaker_hints=[
                TranscriptSegment(
                    text="请介绍 lang chain 项目",
                    start=0,
                    end=1,
                    speaker="SPEAKER_00",
                )
            ],
        )
    )
    assert result.formatted_text == (
        "用户1：请介绍 LangChain 项目。\n用户2：它用于编排大模型应用。"
    )


@pytest.mark.asyncio
async def test_single_mode_rejects_extra_speakers() -> None:
    content = json.dumps(
        {"utterances": [{"speaker": "用户2", "text": "错误标签"}]},
        ensure_ascii=False,
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    refiner = DeepSeekTranscriptRefiner(
        api_key="test-key",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        timeout_seconds=10,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DeepSeekRefinementError):
        await refiner.ainvoke(
            TranscriptRefinementRequest(raw_text="单人内容", speaker_mode="single")
        )
