"""OCR Markdown cleanup behind a typed LangChain Runnable."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from langchain_core.runnables import Runnable, RunnableLambda

from lc_asr_pipeline.schemas.ocr import (
    DocumentRefinementRequest,
    DocumentRefinementResult,
)


class DocumentRefinementError(RuntimeError):
    """Raised when the text model cannot produce usable Markdown."""


class DocumentTextRefiner:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        provider_type: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds
        self._provider_type = provider_type
        self._transport = transport

    def invoke(self, request: DocumentRefinementRequest) -> DocumentRefinementResult:
        return asyncio.run(self.ainvoke(request))

    async def ainvoke(self, request: DocumentRefinementRequest) -> DocumentRefinementResult:
        profile_instruction = (
            "这是简历：保留姓名、联系方式、求职方向、工作经历、项目经历、"
            "教育经历、技能及其时间顺序；不得推断或补写缺失信息。"
            if request.file_attribute == "resume"
            else "这是普通文档：保留章节层级、段落顺序、列表、表格和图注结构。"
        )
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 OCR 文档校对员。完整保留原文事实、数字、姓名、顺序、"
                        "标题、列表和表格，不得总结、删减或补充。只修正有充分上下文"
                        "依据的 OCR 错字、断行和 Markdown 结构。直接输出 Markdown，"
                        "不要使用代码围栏，也不要解释修改过程。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"文件类型：{request.document_kind}\n"
                        f"文件属性：{request.file_attribute}\n"
                        f"{profile_instruction}\n"
                        "请校对以下 OCR Markdown：\n\n"
                        f"{request.markdown_text}"
                    ),
                },
            ],
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
        except (KeyError, TypeError, ValueError) as exc:
            raise DocumentRefinementError(
                "Text provider returned an invalid OCR refinement response"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise DocumentRefinementError("Text provider returned empty OCR Markdown")
        markdown = content.strip()
        if markdown.startswith("```") and markdown.endswith("```"):
            lines = markdown.splitlines()
            markdown = "\n".join(lines[1:-1]).strip()
        if not markdown:
            raise DocumentRefinementError("Text provider returned empty OCR Markdown")
        return DocumentRefinementResult(markdown_text=markdown, model=self._model)


def build_document_refinement_chain(
    refiner: DocumentTextRefiner,
) -> Runnable[DocumentRefinementRequest, DocumentRefinementResult]:
    return RunnableLambda(refiner.invoke, afunc=refiner.ainvoke).with_types(
        input_type=DocumentRefinementRequest,
        output_type=DocumentRefinementResult,
    )
