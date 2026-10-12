"""Resume authoring schemas, image checks, and safe exports."""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from lc_asr_pipeline.api.routes.resume_writer import _validate_photo
from lc_asr_pipeline.resume_templates import (
    RESUME_TEMPLATE_BY_KEY,
    RESUME_TEMPLATES,
)
from lc_asr_pipeline.schemas.resume_writer import (
    ResumeDocumentCreate,
    ResumeDocumentUpdate,
    ResumeProjectEntry,
)
from lc_asr_pipeline.services.image_security import (
    UnsafeImageError,
    normalize_resume_photo,
)
from lc_asr_pipeline.services.resume_export import (
    render_resume_html,
    render_resume_pdf,
)


def _image_bytes(
    image_format: str,
    *,
    size: tuple[int, int] = (32, 24),
    frames: int = 1,
) -> bytes:
    output = BytesIO()
    images = [Image.new("RGB", size, (30 + index * 100, 60, 90)) for index in range(frames)]
    if frames == 1:
        images[0].save(output, format=image_format)
    else:
        images[0].save(
            output,
            format=image_format,
            save_all=True,
            append_images=images[1:],
            duration=100,
            loop=0,
            lossless=True,
        )
    return output.getvalue()


def _document() -> ResumeDocumentUpdate:
    return ResumeDocumentUpdate.model_validate(
        {
            "title": "测试简历",
            "template_key": "local-template-05",
            "theme_color": "#465A73",
            "content": {
                "personal": {
                    "name": "张三",
                    "headline": "平台工程师",
                    "phone": "13800000000",
                    "email": "person@example.com",
                    "summary": "专注可靠的平台交付。",
                },
                "education": [],
                "work": [],
                "projects": [
                    {
                        "id": "project-1",
                        "name": "语音平台",
                        "highlights": ["完成租户隔离"],
                        "technologies": ["FastAPI", "PostgreSQL"],
                    }
                ],
                "skills": ["Python"],
                "certificates": [],
                "self_evaluation": "",
                "source_markdown": "",
            },
        }
    )


def test_resume_document_contract_rejects_unknown_template_and_color() -> None:
    payload = _document()
    assert payload.template_key == "local-template-05"
    assert ResumeDocumentCreate().template_key == "local-template-05"
    assert payload.content.projects[0].name == "语音平台"

    with pytest.raises(ValidationError):
        ResumeDocumentUpdate.model_validate(
            {
                **payload.model_dump(mode="json"),
                "template_key": "copied-template",
                "theme_color": "blue",
            }
        )


def test_resume_template_catalog_contains_only_five_local_templates() -> None:
    expected = {f"local-template-{index:02d}" for index in range(1, 6)}
    assert len(RESUME_TEMPLATES) == 5
    assert set(RESUME_TEMPLATE_BY_KEY) == expected
    assert all(template.group == "local" for template in RESUME_TEMPLATES)
    assert not {"classic", "sidebar", "timeline"} & set(RESUME_TEMPLATE_BY_KEY)


def test_every_resume_template_safely_renders_horizontal_technologies() -> None:
    payload = _document()
    for template in RESUME_TEMPLATES:
        result = render_resume_html(
            title="模板测试",
            template_key=template.key,
            theme_color=template.default_color,
            content_value=payload.content.model_dump(mode="json"),
            photo=None,
        )
        assert f'data-template="{template.key}"' in result
        assert "FastAPI / PostgreSQL" in result
        assert "<script>" not in result


def test_local_template_05_uses_dynamic_flow_and_horizontal_skills() -> None:
    payload = _document()
    payload.content.skills = ["Python", "PostgreSQL", "FastAPI"]
    result = render_resume_html(
        title="05 模板",
        template_key="local-template-05",
        theme_color="#465A73",
        content_value=payload.content.model_dump(mode="json"),
        photo=None,
    )

    assert "template-local-template-05" in result
    assert 'class="skill-tags"' in result
    assert "page-break-inside:avoid" in result
    assert "layout-sidebar" not in result
    assert "qmj-" not in result


def test_resume_project_accepts_tenant_material_lineage() -> None:
    project_id = uuid4()
    project = ResumeProjectEntry(
        id="editor-entry",
        source_project_id=project_id,
        name="数据项目",
    )
    assert project.source_project_id == project_id


def test_resume_html_escapes_user_content_and_embeds_photo() -> None:
    payload = _document()
    payload.content.personal.summary = '<script>alert("x")</script>'
    result = render_resume_html(
        title="<unsafe>",
        template_key="local-template-04",
        theme_color="#262626",
        content_value=payload.content.model_dump(mode="json"),
        photo=("image/png", b"\x89PNG\r\n\x1a\nfake"),
    )

    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "<title>&lt;unsafe&gt;</title>" in result
    assert "data:image/png;base64," in result
    assert "template-local-template-04" in result


def test_resume_photo_validation_checks_size_type_and_signature() -> None:
    _validate_photo("image/jpeg", _image_bytes("JPEG"))

    with pytest.raises(HTTPException) as wrong_signature:
        _validate_photo("image/jpeg", _image_bytes("PNG"))
    assert wrong_signature.value.status_code == 422

    with pytest.raises(HTTPException) as wrong_type:
        _validate_photo("image/gif", b"GIF89a")
    assert wrong_type.value.status_code == 422


@pytest.mark.parametrize(
    ("media_type", "image_format"),
    [
        ("image/jpeg", "JPEG"),
        ("image/png", "PNG"),
        ("image/webp", "WEBP"),
    ],
)
def test_resume_photo_is_fully_decoded_and_reencoded_without_metadata(
    media_type: str,
    image_format: str,
) -> None:
    source = _image_bytes(image_format)
    normalized_type, normalized = normalize_resume_photo(media_type, source)
    assert normalized_type == media_type
    with Image.open(BytesIO(normalized)) as decoded:
        decoded.load()
        assert decoded.format == image_format
        assert decoded.size == (32, 24)
        assert not decoded.getexif()


def test_resume_photo_rejects_truncation_animation_and_excessive_pixels() -> None:
    valid_png = _image_bytes("PNG")
    with pytest.raises(UnsafeImageError):
        normalize_resume_photo("image/png", valid_png[:20])
    with pytest.raises(UnsafeImageError):
        normalize_resume_photo("image/webp", _image_bytes("WEBP", frames=2))
    oversized_buffer = BytesIO()
    Image.new("1", (5000, 5000)).save(oversized_buffer, format="PNG")
    with pytest.raises(UnsafeImageError):
        normalize_resume_photo("image/png", oversized_buffer.getvalue())


def test_resume_pdf_requires_a_real_browser(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Google Chrome or Microsoft Edge"):
        render_resume_pdf("<html></html>", browser_path=tmp_path / "missing")
