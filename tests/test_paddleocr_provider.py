"""PaddleOCR document-provider contract tests."""

from pathlib import Path

import httpx
import pytest

from lc_asr_pipeline.providers import paddleocr
from lc_asr_pipeline.providers.paddleocr import PaddleOCRProvider


@pytest.mark.asyncio
async def test_paddleocr_provider_submits_polls_and_parses_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "fixture.pdf"
    source.write_bytes(b"%PDF-1.7 test")
    calls: list[str] = []

    async def allow_url(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(paddleocr, "enforce_provider_network_policy", allow_url)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url}")
        if request.method == "POST":
            assert b"PaddleOCR-VL-1.6" in request.content
            return httpx.Response(200, json={"data": {"jobId": "job-123"}})
        if str(request.url).endswith("/jobs/job-123"):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "state": "done",
                        "extractProgress": {
                            "totalPages": 1,
                            "extractedPages": 1,
                        },
                        "resultUrl": {
                            "jsonUrl": ("https://paddleocr-store-9.bj.bcebos.com/result.jsonl")
                        },
                    }
                },
            )
        return httpx.Response(
            200,
            text=(
                '{"result":{"layoutParsingResults":'
                '[{"markdown":{"text":"# OCR 标题\\n\\n正文"}}]}}\n'
            ),
        )

    provider = PaddleOCRProvider(
        base_url="https://paddleocr.aistudio-app.com/api/v2/ocr",
        api_key="test-token",
        model="PaddleOCR-VL-1.6",
        poll_interval_seconds=0,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.parse_document(source)

    assert result.provider_job_id == "job-123"
    assert result.page_count == 1
    assert result.markdown_text == "# OCR 标题\n\n正文"
    assert len(calls) == 3


def test_paddleocr_result_host_pattern_accepts_only_official_shards() -> None:
    assert paddleocr.PADDLEOCR_RESULT_HOST_PATTERN.fullmatch("paddleocr-store.bj.bcebos.com")
    assert paddleocr.PADDLEOCR_RESULT_HOST_PATTERN.fullmatch("paddleocr-store-9.bj.bcebos.com")
    assert not paddleocr.PADDLEOCR_RESULT_HOST_PATTERN.fullmatch(
        "paddleocr-store-9.bj.bcebos.com.attacker.example"
    )
    assert not paddleocr.PADDLEOCR_RESULT_HOST_PATTERN.fullmatch("other-store.bj.bcebos.com")
