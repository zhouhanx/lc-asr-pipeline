"""Typed resume-project extraction behind a LangChain Runnable."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import ValidationError

from lc_asr_pipeline.schemas.resume_project import (
    ResumeProjectExtraction,
    ResumeProjectExtractionRequest,
)


class ResumeProjectExtractionError(RuntimeError):
    """Raised when a text model cannot produce safe structured resume data."""


def _validation_field_summary(error: ValidationError) -> str:
    fields = {".".join(str(part) for part in item["loc"]) for item in error.errors() if item["loc"]}
    return ", ".join(sorted(fields))[:1000] or "unknown"


def _json_object(content: str) -> dict[str, Any]:
    normalized = content.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        normalized = "\n".join(lines[1:-1]).strip()
    start = normalized.find("{")
    end = normalized.rfind("}")
    if start < 0 or end < start:
        raise ResumeProjectExtractionError("Text provider returned no resume project JSON object")
    try:
        value = json.loads(normalized[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ResumeProjectExtractionError(
            "Text provider returned invalid resume project JSON"
        ) from exc
    if not isinstance(value, dict):
        raise ResumeProjectExtractionError(
            "Text provider returned a non-object resume project result"
        )
    return value


class ResumeProjectExtractor:
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

    def invoke(
        self,
        request: ResumeProjectExtractionRequest,
    ) -> ResumeProjectExtraction:
        return asyncio.run(self.ainvoke(request))

    async def ainvoke(
        self,
        request: ResumeProjectExtractionRequest,
    ) -> ResumeProjectExtraction:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是简历项目结构化抽取器。只能抽取输入中明确存在的信息，"
                        "不得推断、补写、合并不同项目或修改时间。一个人可以有多个项目，"
                        "必须按原文顺序逐个输出。公司名称只在原文明确关联该项目时填写。"
                        "start_date 和 end_date 保留原始时间文字；仍在进行的项目将 "
                        "is_current 设为 true。source_excerpt 保存能证明项目归属、时间、"
                        "公司和角色的短原文。project_background、主要职责 "
                        "responsibilities、项目职责 project_responsibilities、项目成果 "
                        "project_outcomes 只能逐字依据输入提取；没有则使用 null 或空数组，"
                        "绝不补充。每个项目必须评分：architecture_rationality 表示架构"
                        "合理性，description_credibility 表示描述可信度，二者越高越好；"
                        "embellishment_risk 表示美化风险，越高风险越大。每项 1 到 10 分"
                        "并给出仅基于原文的 reason；证据不足时理由必须明确写证据不足。"
                        "没有项目时 projects 输出空数组。"
                        "只输出一个 JSON 对象，不要 Markdown 或解释。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "输出字段：candidate_name、phone、email、current_company、projects。"
                        "每个 projects 元素必须包含 project_name、company_name、role_name、"
                        "start_date、end_date、is_current、description、responsibilities、"
                        "technologies、project_background、project_responsibilities、"
                        "project_outcomes、source_excerpt、scoring。scoring 必须包含 "
                        "architecture_rationality、description_credibility、"
                        "embellishment_risk，每项包含 score 和 reason。\n\n"
                        f"简历 Markdown：\n{request.markdown_text}"
                    ),
                },
            ],
            "stream": False,
            "max_tokens": 32768,
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
            raise ResumeProjectExtractionError(
                "Text provider returned an invalid resume extraction response"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ResumeProjectExtractionError(
                "Text provider returned an empty resume extraction response"
            )
        try:
            return ResumeProjectExtraction.model_validate(
                {**_json_object(content), "model": self._model}
            )
        except ValidationError as exc:
            raise ResumeProjectExtractionError(
                "Text provider returned invalid resume project fields: "
                f"{_validation_field_summary(exc)}"
            ) from exc


def build_resume_project_extraction_chain(
    extractor: ResumeProjectExtractor,
) -> Runnable[ResumeProjectExtractionRequest, ResumeProjectExtraction]:
    return RunnableLambda(extractor.invoke, afunc=extractor.ainvoke).with_types(
        input_type=ResumeProjectExtractionRequest,
        output_type=ResumeProjectExtraction,
    )
