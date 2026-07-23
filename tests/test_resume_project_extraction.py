"""Resume project structured-extraction tests."""

import httpx
import pytest

from lc_asr_pipeline.schemas.resume_project import ResumeProjectExtractionRequest
from lc_asr_pipeline.services.resume_project_extraction import (
    ResumeProjectExtractionError,
    ResumeProjectExtractor,
)


@pytest.mark.asyncio
async def test_resume_extractor_keeps_multiple_projects_and_lineage_fields() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "```json\n"
                                '{"candidate_name":"张三","phone":null,"email":null,'
                                '"current_company":"示例公司","projects":['
                                '{"project_name":"数仓升级","company_name":"甲公司",'
                                '"role_name":"数据工程师","start_date":"2022.03",'
                                '"end_date":"2022.12","is_current":false,'
                                '"description":"升级数仓","responsibilities":["建模"],'
                                '"technologies":["Spark"],'
                                '"project_background":"旧数仓性能不足",'
                                '"project_responsibilities":["维度建模"],'
                                '"project_outcomes":["查询提速"],'
                                '"scoring":{'
                                '"architecture_rationality":{"score":8,"reason":"分层明确"},'
                                '"description_credibility":{"score":7,"reason":"职责具体"},'
                                '"embellishment_risk":{"score":3,"reason":"未见夸大表述"}},'
                                '"source_excerpt":"2022.03-2022.12 甲公司 数仓升级"},'
                                '{"project_name":"指标平台","company_name":"示例公司",'
                                '"role_name":"负责人","start_date":"2023.01",'
                                '"end_date":"至今","is_current":true,'
                                '"description":"建设指标平台","responsibilities":[],'
                                '"technologies":["Flink","Doris"],'
                                '"project_background":null,'
                                '"project_responsibilities":[],'
                                '"project_outcomes":[],'
                                '"scoring":{'
                                '"architecture_rationality":{"score":6,"reason":"架构证据较少"},'
                                '"description_credibility":{"score":5,"reason":"成果证据不足"},'
                                '"embellishment_risk":{"score":5,"reason":"证据不足"}},'
                                '"source_excerpt":"2023.01-至今 指标平台"}]}'
                                "\n```"
                            )
                        }
                    }
                ]
            },
        )

    extractor = ResumeProjectExtractor(
        api_key="test-key",
        base_url="https://api.example.com/v1",
        model="test-model",
        timeout_seconds=10,
        provider_type="openai_compatible",
        transport=httpx.MockTransport(handler),
    )
    result = await extractor.ainvoke(
        ResumeProjectExtractionRequest(markdown_text="# 张三\n\n## 项目经历")
    )

    assert result.candidate_name == "张三"
    assert len(result.projects) == 2
    assert result.projects[0].company_name == "甲公司"
    assert result.projects[0].start_date == "2022.03"
    assert result.projects[1].is_current is True
    assert result.projects[1].technologies == ["Flink", "Doris"]
    assert result.projects[0].project_background == "旧数仓性能不足"
    assert result.projects[0].project_outcomes == ["查询提速"]
    assert result.projects[0].scoring.architecture_rationality.score == 8
    assert result.projects[1].project_background is None


@pytest.mark.asyncio
async def test_resume_extractor_rejects_non_json_output() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "无法提取"}}]},
        )

    extractor = ResumeProjectExtractor(
        api_key="test-key",
        base_url="https://api.example.com/v1",
        model="test-model",
        timeout_seconds=10,
        provider_type="openai_compatible",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ResumeProjectExtractionError):
        await extractor.ainvoke(ResumeProjectExtractionRequest(markdown_text="# 没有项目"))


@pytest.mark.asyncio
async def test_resume_extractor_reports_invalid_field_paths_without_values() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"candidate_name":"候选人","projects":[{'
                                '"project_name":"项目","scoring":{'
                                '"architecture_rationality":{"score":11,"reason":"secret"},'
                                '"description_credibility":{"score":8,"reason":"具体"},'
                                '"embellishment_risk":{"score":2,"reason":"较低"}}}]}'
                            )
                        }
                    }
                ]
            },
        )

    extractor = ResumeProjectExtractor(
        api_key="test-key",
        base_url="https://api.example.com/v1",
        model="test-model",
        timeout_seconds=10,
        provider_type="openai_compatible",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ResumeProjectExtractionError) as captured:
        await extractor.ainvoke(ResumeProjectExtractionRequest(markdown_text="# 候选人"))

    message = str(captured.value)
    assert "projects.0.scoring.architecture_rationality.score" in message
    assert "secret" not in message


@pytest.mark.asyncio
async def test_resume_extractor_normalizes_explicit_null_optional_fields() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"candidate_name":null,"projects":[{'
                                '"project_name":null,"responsibilities":null,'
                                '"technologies":null,"project_responsibilities":null,'
                                '"project_outcomes":null,"scoring":{'
                                '"architecture_rationality":{"score":5,"reason":"证据不足"},'
                                '"description_credibility":{"score":5,"reason":"证据不足"},'
                                '"embellishment_risk":{"score":5,"reason":"证据不足"}}}]}'
                            )
                        }
                    }
                ]
            },
        )

    extractor = ResumeProjectExtractor(
        api_key="test-key",
        base_url="https://api.example.com/v1",
        model="test-model",
        timeout_seconds=10,
        provider_type="openai_compatible",
        transport=httpx.MockTransport(handler),
    )

    result = await extractor.ainvoke(ResumeProjectExtractionRequest(markdown_text="# 未识别简历"))

    assert result.candidate_name == "未识别姓名"
    assert result.projects[0].project_name == "未命名项目"
    assert result.projects[0].responsibilities == []
    assert result.projects[0].project_responsibilities == []
    assert result.projects[0].project_outcomes == []
