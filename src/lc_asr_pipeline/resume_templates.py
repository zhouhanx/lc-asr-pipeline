"""Authoritative registry for the five local resume templates."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_RESUME_TEMPLATE_KEY = "local-template-05"


@dataclass(frozen=True, slots=True)
class ResumeTemplateDefinition:
    key: str
    name: str
    description: str
    group: str
    layout: str
    header_style: str
    section_style: str
    density: str
    default_color: str
    variant: int


RESUME_TEMPLATES = (
    ResumeTemplateDefinition(
        key="local-template-01",
        name="本地模板 01",
        description="青灰金色顶栏 · 绶带分节 · 高密度单栏",
        group="local",
        layout="local_01",
        header_style="banner",
        section_style="ribbon",
        density="compact",
        default_color="#4F7180",
        variant=1,
    ),
    ResumeTemplateDefinition(
        key="local-template-02",
        name="本地模板 02",
        description="居中标题 · 浅蓝通栏 · 清晰单栏",
        group="local",
        layout="local_02",
        header_style="centered",
        section_style="band",
        density="compact",
        default_color="#3C82B4",
        variant=2,
    ),
    ResumeTemplateDefinition(
        key="local-template-03",
        name="本地模板 03",
        description="蓝色页眉 · 联系人网格 · 长下划线分节",
        group="local",
        layout="local_03",
        header_style="topbar",
        section_style="underline",
        density="compact",
        default_color="#5576B6",
        variant=3,
    ),
    ResumeTemplateDefinition(
        key="local-template-04",
        name="本地模板 04",
        description="黑白极简 · 居中身份 · ATS 友好",
        group="local",
        layout="local_04",
        header_style="minimal",
        section_style="line",
        density="compact",
        default_color="#262626",
        variant=4,
    ),
    ResumeTemplateDefinition(
        key=DEFAULT_RESUME_TEMPLATE_KEY,
        name="本地模板 05 · 技术履历优化",
        description="深灰蓝绶带 · 纵向轨道 · 项目技术优先 · 自然分页",
        group="local",
        layout="local_05",
        header_style="resume_mark",
        section_style="tracked_ribbon",
        density="compact",
        default_color="#465A73",
        variant=5,
    ),
)

RESUME_TEMPLATE_BY_KEY = {template.key: template for template in RESUME_TEMPLATES}
RESUME_TEMPLATE_KEYS = frozenset(RESUME_TEMPLATE_BY_KEY)

assert len(RESUME_TEMPLATES) == 5
assert len(RESUME_TEMPLATE_BY_KEY) == len(RESUME_TEMPLATES)


def get_resume_template(key: str) -> ResumeTemplateDefinition:
    """Return a registered local template or raise a controlled lookup error."""
    try:
        return RESUME_TEMPLATE_BY_KEY[key]
    except KeyError as error:
        raise ValueError("unsupported resume template") from error
