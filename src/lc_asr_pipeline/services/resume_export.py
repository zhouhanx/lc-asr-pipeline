"""Safe HTML rendering and headless-browser PDF export for resumes."""

from __future__ import annotations

import base64
import html
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from lc_asr_pipeline.resume_templates import get_resume_template
from lc_asr_pipeline.schemas.resume_writer import ResumeContent

_BROWSER_CANDIDATES = (
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
)
_SUPPORTED_BROWSER_EXECUTABLES = {
    "google chrome",
    "google-chrome",
    "google-chrome-stable",
    "chrome.exe",
    "microsoft edge",
    "microsoft-edge",
    "microsoft-edge-stable",
    "msedge.exe",
}


def _is_supported_browser(browser: Path) -> bool:
    return browser.is_file() and browser.name.casefold() in _SUPPORTED_BROWSER_EXECUTABLES


def _safe(value: object) -> str:
    return html.escape(str(value or ""))


def _lines(values: list[str]) -> str:
    items = "".join(f"<li>{_safe(value)}</li>" for value in values if value.strip())
    return f"<ul>{items}</ul>" if items else ""


def _tags(values: list[str]) -> str:
    items = "".join(f"<span>{_safe(value)}</span>" for value in values if value.strip())
    return f'<div class="skill-tags">{items}</div>' if items else ""


def _period(start: str, end: str) -> str:
    return " — ".join(value for value in (start.strip(), end.strip()) if value)


def _section(title: str, body: str, *, class_name: str = "") -> str:
    if not body:
        return ""
    return f'<section class="resume-section {class_name}"><h2>{_safe(title)}</h2>{body}</section>'


def _entry(title: str, subtitle: str, period: str, body: str) -> str:
    return (
        '<article class="entry"><div class="entry-heading"><div>'
        f"<h3>{_safe(title)}</h3><p>{_safe(subtitle)}</p></div>"
        f"<time>{_safe(period)}</time></div>{body}</article>"
    )


def render_resume_html(
    *,
    title: str,
    template_key: str,
    theme_color: str,
    content_value: dict[str, Any],
    photo: tuple[str, bytes] | None,
) -> str:
    template = get_resume_template(template_key)
    content = ResumeContent.model_validate(content_value)
    personal = content.personal
    photo_html = ""
    if photo:
        media_type, image_bytes = photo
        encoded = base64.b64encode(image_bytes).decode("ascii")
        photo_html = (
            f'<img class="portrait" alt="个人照片" src="data:{media_type};base64,{encoded}">'
        )
    contacts = [
        value
        for value in (
            personal.phone,
            personal.email,
            personal.location,
            personal.website,
        )
        if value.strip()
    ]
    contacts_html = "".join(f"<span>{_safe(item)}</span>" for item in contacts)
    education = "".join(
        _entry(
            item.school,
            " · ".join(value for value in (item.degree, item.major) if value),
            _period(item.start_date, item.end_date),
            f"<p>{_safe(item.description)}</p>" if item.description else "",
        )
        for item in content.education
        if any((item.school, item.degree, item.major, item.description))
    )
    work = "".join(
        _entry(
            item.role,
            item.company,
            _period(item.start_date, item.end_date),
            _lines(item.highlights),
        )
        for item in content.work
        if any((item.company, item.role, *item.highlights))
    )
    projects = "".join(
        _entry(
            item.name,
            " · ".join(value for value in (item.company, item.role) if value),
            _period(item.start_date, item.end_date),
            (
                (f"<p>{_safe(item.summary)}</p>" if item.summary else "")
                + _lines(item.highlights)
                + (
                    f'<p class="technologies"><strong>技术栈</strong> · '
                    f"{_safe(' / '.join(item.technologies))}</p>"
                    if item.technologies
                    else ""
                )
            ),
        )
        for item in content.projects
        if any((item.name, item.summary, *item.highlights))
    )
    summary_parts = [
        f"<p>{_safe(value)}</p>"
        for value in (personal.summary, content.self_evaluation)
        if value.strip()
    ]
    summary = "".join(summary_parts)
    skills = _section("专业技能", _tags(content.skills), class_name="compact")
    certificates = _section(
        "证书荣誉",
        _lines(content.certificates),
        class_name="compact",
    )
    if template.key == "local-template-05":
        main_sections = "".join(
            (
                _section("自我评价", summary),
                _section("工作经历", work),
                _section("代表项目", projects),
                skills,
                _section("教育背景", education),
                certificates,
            )
        )
    else:
        main_sections = "".join(
            (
                _section("个人简介", summary),
                _section("教育背景", education),
                _section("工作经历", work),
                _section("项目经历", projects),
                skills,
                certificates,
            )
        )
    resume_body = (
        f'<header>{photo_html}<div class="identity"><h1>{_safe(personal.name)}</h1>'
        f"<p>{_safe(personal.headline)}</p>"
        f'<div class="contacts">{contacts_html}</div>'
        f'</div></header><main class="content">{main_sections}</main>'
    )
    safe_title = _safe(title)
    template_classes = " ".join(
        (
            f"template-{template_key}",
            f"layout-{template.layout}",
        )
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_title}</title>
<style>
@page {{ size:A4; margin:12mm 14mm; }}
:root {{ --accent:{theme_color}; --ink:#18202b; --muted:#667085; --line:#d0d5dd; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#eceff3; color:var(--ink);
  font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",Arial,sans-serif; }}
.resume {{ width:210mm; min-height:297mm; margin:0 auto; background:#fff; padding:12mm 14mm;
  font-size:9.6pt; line-height:1.48; }}
header {{ display:flex; align-items:center; gap:20px; border-bottom:3px solid var(--accent);
  padding-bottom:12px; margin-bottom:14px; position:relative; }}
.portrait {{ width:28mm; height:35mm; object-fit:cover; border-radius:4px; flex:none; }}
.identity {{ flex:1; }}
h1 {{ margin:0; font-size:24pt; line-height:1.15; letter-spacing:1px; }}
.identity>p {{ margin:5px 0 0; color:var(--accent); font-size:10pt; font-weight:700; }}
.contacts {{ display:flex; flex-wrap:wrap; gap:5px 18px; margin-top:10px; color:var(--muted);
  font-size:8.5pt; }}
.contacts span {{ overflow-wrap:anywhere; }}
h2 {{ margin:0 0 10px; color:var(--accent); font-size:14pt; border-bottom:1px solid var(--line);
  padding-bottom:5px; }}
.resume-section {{ margin-bottom:13px; break-inside:auto; }}
.resume-section>h2 {{ break-after:avoid-page; page-break-after:avoid; }}
.resume-section>h2+* {{ break-before:avoid-page; page-break-before:avoid; }}
.entry {{ margin-bottom:9px; break-inside:avoid; page-break-inside:avoid; }}
.entry-heading {{ display:flex; justify-content:space-between; gap:14px; align-items:flex-start; }}
h3 {{ margin:0; font-size:10pt; }}
.entry-heading p {{ margin:2px 0 0; color:var(--muted); }}
time {{ color:var(--muted); font-size:8.5pt; white-space:nowrap; }}
p {{ margin:4px 0; white-space:pre-wrap; }}
ul {{ margin:4px 0; padding-left:18px; }}
li {{ margin:2px 0; }}
.technologies {{ display:flex; flex-wrap:wrap; align-items:center; gap:3px 8px; color:var(--muted);
  font-size:8.5pt; }}
.skill-tags {{ display:flex; flex-wrap:wrap; gap:4px 8px; }}
.skill-tags span {{ padding:2px 7px; border:1px solid color-mix(in srgb,var(--accent) 35%,white);
  color:var(--accent); }}
.compact li {{ overflow-wrap:anywhere; }}
.template-local-template-01 header {{ border:0; padding-bottom:13px; }}
.template-local-template-01 header:after {{ content:""; position:absolute;
  left:0; right:0; bottom:0;
  height:7px; background:linear-gradient(105deg,var(--accent) 0 62%,#c8a66a 62%); }}
.template-local-template-01 h2,.template-local-template-05 h2 {{ display:inline-block;
  min-width:48mm; padding:3px 14px; color:#fff; background:var(--accent); border:0;
  letter-spacing:2px; position:relative; }}
.template-local-template-01 h2:after,.template-local-template-05 h2:after {{ content:"";
  position:absolute; right:-14px; top:0; border-top:13px solid transparent;
  border-bottom:13px solid transparent; border-left:14px solid var(--accent); }}
.template-local-template-02 header {{ justify-content:center; text-align:center; border:0; }}
.template-local-template-02 header .portrait {{ order:2; position:absolute; right:0; top:0; }}
.template-local-template-02 header .contacts {{ justify-content:center; }}
.template-local-template-02 h2 {{ padding:4px 10px 4px 34mm; color:var(--accent);
  background:color-mix(in srgb,var(--accent) 15%,white); border:0; position:relative; }}
.template-local-template-02 h2:before {{ content:""; position:absolute; inset:0 auto 0 0;
  width:29mm; background:var(--accent); }}
.template-local-template-03 header {{ padding-top:15mm; }}
.template-local-template-03 header:before {{ content:"PERSONAL RESUME"; position:absolute;
  left:0; right:0; top:0; padding:4px 10px; color:#fff; background:var(--accent);
  font-size:16pt; letter-spacing:2px; }}
.template-local-template-03 h2 {{ border-bottom:2px solid #999; color:var(--accent); }}
.template-local-template-04 header {{ justify-content:center; text-align:center;
  border-bottom:1px solid #333; }}
.template-local-template-04 header .portrait {{ order:2; position:absolute; right:0; top:0; }}
.template-local-template-04 header .contacts {{ justify-content:center; }}
.template-local-template-04 h2 {{ color:#222; border-color:#333; }}
.template-local-template-05 {{ padding:10mm 12mm; font-size:9.3pt; line-height:1.42; }}
.template-local-template-05 header {{ min-height:39mm; border-bottom:1px solid var(--line);
  padding:12mm 0 8px 0; }}
.template-local-template-05 header:before {{ content:"RESUME"; position:absolute; left:0; top:0;
  padding:5px 11px; color:#fff; background:var(--accent); font-size:17pt; font-weight:900; }}
.template-local-template-05 header .portrait {{ order:2; margin-left:auto; }}
.template-local-template-05 .contacts {{ display:grid; grid-template-columns:1fr 1fr; }}
.template-local-template-05 .resume-section {{ padding-left:6mm; margin-bottom:10px;
  border-left:1px solid #c7cbd1; }}
.template-local-template-05 .entry-heading h3,.template-local-template-05 .technologies strong {{
  color:var(--accent); }}
.template-local-template-05 .technologies {{ padding:3px 6px;
  background:color-mix(in srgb,var(--accent) 6%,white); }}
@media(max-width:800px) {{ .resume {{ width:100%; min-height:auto; padding:28px; }} }}
@media print {{ body {{ background:#fff; }}
  .resume {{ width:auto; min-height:0; margin:0; padding:0; }}
  .template-local-template-05 {{ font-size:9.3pt; }} }}
</style>
</head>
<body>
<div class="resume {template_classes}" data-template="{_safe(template_key)}">
{resume_body}
</div>
</body>
</html>"""


def render_resume_pdf(html_text: str, *, browser_path: Path | None = None) -> bytes:
    browser = browser_path or next(
        (candidate for candidate in _BROWSER_CANDIDATES if candidate.is_file()),
        None,
    )
    if browser is None or not _is_supported_browser(browser):
        raise RuntimeError("PDF export requires Google Chrome or Microsoft Edge")
    with tempfile.TemporaryDirectory(prefix="lc-resume-pdf-") as directory:
        temp_path = Path(directory)
        html_path = temp_path / "resume.html"
        pdf_path = temp_path / "resume.pdf"
        profile_path = temp_path / "browser-profile"
        html_path.write_text(html_text, encoding="utf-8")
        process = subprocess.Popen(
            [
                str(browser),
                "--headless=new",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-extensions",
                "--disable-sync",
                "--no-first-run",
                "--no-pdf-header-footer",
                "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=1000",
                f"--user-data-dir={profile_path}",
                f"--print-to-pdf={pdf_path}",
                html_path.as_uri(),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if pdf_path.is_file() and pdf_path.stat().st_size > 100:
                    pdf = pdf_path.read_bytes()
                    if pdf.startswith(b"%PDF-"):
                        return pdf
                if process.poll() is not None:
                    break
                time.sleep(0.1)
            raise RuntimeError("Headless browser failed to generate the PDF")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
