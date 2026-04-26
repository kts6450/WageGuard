"""PROPOSAL.md -> PROPOSAL.html -> PROPOSAL.pdf

- markdown 라이브러리로 HTML 변환 (tables, fenced_code, attr_list)
- 한글 친화 CSS (Malgun Gothic / Noto Sans KR fallback) 및 A4 인쇄 스타일
- 이미지 base64 임베드로 자가완결 HTML 생성
- Microsoft Edge (또는 Chrome) headless --print-to-pdf 로 PDF 출력
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
MD_PATH = ROOT / "PROPOSAL.md"
HTML_PATH = ROOT / "PROPOSAL.html"
PDF_PATH = ROOT / "PROPOSAL.pdf"

CSS = r"""
@page {
  size: A4;
  margin: 12mm 12mm 12mm 12mm;
}
html, body {
  font-family: "Malgun Gothic", "맑은 고딕", "Noto Sans KR", "Apple SD Gothic Neo", sans-serif;
  font-size: 9.4pt;
  line-height: 1.38;
  color: #000000;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
body { margin: 0; }
h1 {
  text-align: center;
  font-size: 15pt;
  font-weight: 700;
  color: #000000;
  letter-spacing: -0.2px;
  border: 1.5px solid #000000;
  background: #d9d9d9;
  padding: 8px 8px;
  margin: 0 0 8px 0;
}
h2 {
  font-size: 11.5pt;
  font-weight: 700;
  color: #000000;
  background: #d9d9d9;
  border: 1px solid #000000;
  padding: 3px 8px;
  margin: 8px 0 4px 0;
  page-break-after: avoid;
}
h3 {
  font-size: 10.5pt;
  font-weight: 700;
  color: #1f2937;
  margin: 6px 0 3px 0;
  padding-left: 5px;
  border-left: 3px solid #000000;
  page-break-after: avoid;
}
h4 {
  font-size: 10pt;
  font-weight: 700;
  color: #374151;
  margin: 5px 0 2px 0;
}
p { margin: 3px 0; text-align: justify; }
ul, ol { margin: 3px 0 3px 18px; padding: 0; }
li { margin: 1px 0; }
strong { color: #000000; font-weight: 700; }
em { color: #000000; font-style: normal; font-weight: 700; text-decoration: underline; }
hr {
  border: none;
  border-top: 1px solid #000000;
  margin: 6px 0;
}
blockquote {
  border-left: 3px solid #000000;
  background: #f4f4f4;
  margin: 4px 0;
  padding: 4px 8px;
  color: #000000;
  font-style: normal;
}
code {
  font-family: "Consolas", "D2Coding", "Courier New", monospace;
  background: #f1f1f1;
  padding: 0 3px;
  border-radius: 2px;
  font-size: 9pt;
}
pre {
  background: #f6f6f6;
  border: 1px solid #cccccc;
  border-radius: 0;
  padding: 7px 9px;
  font-size: 8.5pt;
  line-height: 1.35;
  overflow-x: auto;
  page-break-inside: avoid;
  margin: 5px 0;
}
pre code { background: transparent; padding: 0; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 5px 0;
  font-size: 9pt;
  page-break-inside: avoid;
}
th, td {
  border: 0.7px solid #000000;
  padding: 3px 5px;
  vertical-align: top;
}
th {
  background: #d9d9d9;
  color: #000000;
  font-weight: 700;
  text-align: center;
}
tr:nth-child(even) td { background: #fafafa; }
img {
  max-width: 84%;
  max-height: 62mm;
  height: auto;
  display: block;
  margin: 3px auto;
  page-break-inside: avoid;
}
a { color: #000000; text-decoration: underline; }
a:hover { text-decoration: underline; }

/* 표지 정보 박스 — 양식 1쪽 「아이디어명」 위 메타 영역 */
.cover-meta {
  border: 0.8px solid #000000;
  padding: 0;
  margin: 0 0 10px 0;
}
.cover-meta table {
  margin: 0;
  font-size: 8.6pt;
}
.cover-meta th, .cover-meta td {
  border: 0.5px solid #000000;
  padding: 3px 6px;
}

/* 시스템 개요 파이프라인 다이어그램 */
.pipeline {
  margin: 6px 0 8px 0;
  page-break-inside: avoid;
}
.pipe-row {
  display: flex;
  gap: 6px;
  margin: 0 0 4px 0;
}
.pipe-row.two > .pipe-box { flex: 1 1 50%; }
.pipe-box {
  border: 1px solid #000000;
  background: #ffffff;
  padding: 0;
  margin: 0 0 0 0;
}
.pipe-box.step {
  background: #fafafa;
}
.pipe-title {
  background: #d9d9d9;
  border-bottom: 1px solid #000000;
  padding: 2px 6px;
  font-weight: 700;
  font-size: 9.4pt;
}
.pipe-body {
  padding: 4px 8px;
  font-size: 9.0pt;
  line-height: 1.4;
}
.pipe-body em {
  font-style: italic;
  font-weight: 400;
  text-decoration: none;
  color: #555555;
}
.pipe-arrow {
  text-align: center;
  font-size: 11pt;
  font-weight: 700;
  color: #000000;
  margin: 0;
  line-height: 1.1;
}
.pipe-end {
  text-align: center;
  font-weight: 700;
  border: 1.2px solid #000000;
  background: #d9d9d9;
  padding: 4px 8px;
  margin: 2px auto 0 auto;
  font-size: 9.6pt;
}

/* 한눈에 보는 출품작 요약 박스 — 첫 페이지 임팩트 */
.summary-box {
  border: 1.5px solid #000000;
  background: #fafafa;
  padding: 6px 8px 4px 8px;
  margin: 6px 0 8px 0;
  page-break-inside: avoid;
}
.summary-box p:first-child {
  text-align: center;
  font-weight: 700;
  font-size: 10.5pt;
  background: #d9d9d9;
  border: 0.8px solid #000000;
  padding: 3px 6px;
  margin: 0 0 6px 0;
}
.summary-box table {
  margin: 0;
  font-size: 8.8pt;
}
.summary-box th {
  background: #efefef;
  width: 22%;
  text-align: center;
}
.summary-box td {
  background: #ffffff;
}
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>WageGuard — 아이디어 제안서</title>
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def embed_image_as_data_uri(match: re.Match[str]) -> str:
    alt = match.group(1)
    rel = match.group(2)
    img_path = (ROOT / rel).resolve()
    if not img_path.exists():
        return match.group(0)
    ext = img_path.suffix.lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "svg": "image/svg+xml",
    }.get(ext, "application/octet-stream")
    data = base64.b64encode(img_path.read_bytes()).decode("ascii")
    return f"![{alt}](data:{mime};base64,{data})"


def find_browser() -> str | None:
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def main() -> int:
    md_text = MD_PATH.read_text(encoding="utf-8")

    md_text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", embed_image_as_data_uri, md_text)

    html_body = markdown.markdown(
        md_text,
        extensions=[
            "extra",
            "tables",
            "fenced_code",
            "sane_lists",
            "attr_list",
            "toc",
        ],
        output_format="html5",
    )

    html = HTML_TEMPLATE.format(css=CSS, body=html_body)
    HTML_PATH.write_text(html, encoding="utf-8")
    print(f"[OK] HTML  -> {HTML_PATH}")

    browser = find_browser()
    if not browser:
        print("[WARN] Edge/Chrome not found. PDF skipped. HTML 만 생성됨.")
        return 0

    file_url = HTML_PATH.resolve().as_uri()
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_PATH}",
        "--print-to-pdf-no-header",
        file_url,
    ]
    print("[RUN] " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0:
        print("[ERR] browser stderr:", res.stderr[:1500])
        return res.returncode
    if PDF_PATH.exists():
        size_kb = PDF_PATH.stat().st_size / 1024
        print(f"[OK] PDF   -> {PDF_PATH}  ({size_kb:,.1f} KB)")
    else:
        print("[ERR] PDF not produced")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
