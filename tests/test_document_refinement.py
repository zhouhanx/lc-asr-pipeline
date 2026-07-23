"""Document-profile refinement prompt tests."""

import json

import httpx
import pytest

from lc_asr_pipeline.schemas.ocr import DocumentRefinementRequest
from lc_asr_pipeline.services.document_refinement import DocumentTextRefiner


@pytest.mark.asyncio
async def test_resume_attribute_adds_resume_preservation_instruction() -> None:
    captured_user_prompt = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_user_prompt
        payload = json.loads(request.content)
        captured_user_prompt = payload["messages"][1]["content"]
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "# 姓名\n\n工作经历"}}]},
        )

    refiner = DocumentTextRefiner(
        api_key="test-key",
        base_url="https://api.example.com/v1",
        model="test-model",
        timeout_seconds=10,
        provider_type="openai_compatible",
        transport=httpx.MockTransport(handler),
    )
    result = await refiner.ainvoke(
        DocumentRefinementRequest(
            markdown_text="# 姓名\n\n工作经历",
            document_kind="pdf",
            file_attribute="resume",
        )
    )

    assert result.markdown_text == "# 姓名\n\n工作经历"
    assert "文件属性：resume" in captured_user_prompt
    assert "不得推断或补写缺失信息" in captured_user_prompt
