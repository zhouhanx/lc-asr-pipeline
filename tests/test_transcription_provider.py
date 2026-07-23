from pathlib import Path

import httpx

from lc_asr_pipeline.providers.openai_compatible import OpenAICompatibleASRProvider
from lc_asr_pipeline.providers.stepfun import StepFunASRProvider
from lc_asr_pipeline.schemas.transcription import TranscriptionRequest
from lc_asr_pipeline.services.transcription_chain import build_transcription_chain


def test_langchain_runnable_calls_openai_compatible_provider(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"RIFF-test")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer service-secret"
        assert request.url.path == "/v1/audio/transcriptions"
        return httpx.Response(
            200,
            json={
                "text": "测试文本",
                "language": "Chinese",
                "segments": [{"text": "测试文本", "start": 0, "end": 1.2}],
            },
        )

    provider = OpenAICompatibleASRProvider(
        name="local-mlx",
        base_url="http://model.test",
        api_key="service-secret",
        model="qwen3-asr-1.7b-mlx-8bit",
        transport=httpx.MockTransport(handler),
    )
    result = build_transcription_chain(provider).invoke(
        TranscriptionRequest(audio_path=audio_path, language="Chinese")
    )

    assert result.text == "测试文本"
    assert result.provider == "local-mlx"
    assert result.segments[0].end == 1.2


def test_provider_does_not_duplicate_v1_path() -> None:
    provider = OpenAICompatibleASRProvider(
        name="remote",
        base_url="https://api.example.com/v1/",
        api_key="secret",
        model="asr",
    )
    assert provider.endpoint("/v1/audio/transcriptions") == (
        "https://api.example.com/v1/audio/transcriptions"
    )


def test_langchain_runnable_calls_stepfun_sse_provider(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"test-audio")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer stepfun-secret"
        assert request.url.path == "/v1/audio/asr/sse"
        payload = request.read().decode()
        assert '"model":"stepaudio-2.5-asr"' in payload
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=(
                'data: {"type":"transcript.text.delta","delta":"测试",'
                '"start_time":0,"end_time":800}\n\n'
                'data: {"type":"transcript.text.done","text":"测试文本"}\n\n'
            ),
        )

    provider = StepFunASRProvider(
        name="StepFun",
        base_url="https://api.stepfun.com/v1",
        api_key="stepfun-secret",
        transport=httpx.MockTransport(handler),
    )
    result = build_transcription_chain(provider).invoke(
        TranscriptionRequest(audio_path=audio_path, language="Chinese", diarize=False)
    )

    assert result.text == "测试文本"
    assert result.provider == "StepFun"
    assert result.segments[0].end == 0.8
