#!/usr/bin/env python3
"""Render the resume-tailoring case study markdown to HTML and PDF."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from markdown import markdown


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "docs/ai-artifacts/resume-tailoring-evidence-grounded-case-study.md"
DEFAULT_HTML = ROOT / "docs/ai-artifacts/resume-tailoring-evidence-grounded-case-study.html"
DEFAULT_PDF = ROOT / "docs/ai-artifacts/resume-tailoring-evidence-grounded-case-study.pdf"


CSS = """
:root {
  color: #17212b;
  background: #ffffff;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 11pt;
  line-height: 1.54;
}
@page { size: Letter; margin: 0.64in 0.68in 0.7in 0.68in; }
* { box-sizing: border-box; }
body {
  margin: 0;
  color: #17212b;
  background: #ffffff;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
main { max-width: 8.05in; margin: 0 auto; }
h1 {
  margin: 0 0 0.18in;
  color: #0f2537;
  font-size: 27pt;
  line-height: 1.08;
  letter-spacing: 0;
  font-weight: 780;
}
h2 {
  margin: 0.32in 0 0.1in;
  color: #0f2537;
  font-size: 16.4pt;
  line-height: 1.22;
  font-weight: 740;
  break-after: avoid;
  page-break-after: avoid;
}
p { margin: 0 0 0.105in; }
ul, ol { margin: 0.02in 0 0.14in 0.24in; padding-left: 0.18in; }
li { margin: 0.025in 0; }
strong { font-weight: 730; }
em { color: #34495a; }
a { color: #0d5f73; text-decoration: none; }
code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.91em;
  color: #17324d;
  background: #eef4f7;
  border: 1px solid #d9e5ea;
  border-radius: 4px;
  padding: 0.02in 0.045in;
}
pre {
  margin: 0.13in 0 0.18in;
  padding: 0.14in 0.16in;
  background: #f5f8fa;
  border: 1px solid #d8e3e8;
  border-radius: 8px;
  overflow: hidden;
  white-space: pre-wrap;
  break-inside: auto;
  page-break-inside: auto;
}
pre code {
  background: transparent;
  border: 0;
  padding: 0;
  color: #1c2f3e;
  font-size: 8.85pt;
  line-height: 1.4;
  white-space: pre-wrap;
}
table {
  width: 100%;
  margin: 0.12in 0 0.2in;
  border-collapse: collapse;
  font-size: 8.65pt;
  line-height: 1.35;
  break-inside: avoid;
  page-break-inside: avoid;
}
th {
  text-align: left;
  background: #edf3f6;
  color: #102838;
  font-weight: 730;
  border-bottom: 1.4px solid #9db2bd;
}
th, td {
  padding: 0.052in 0.058in;
  border-bottom: 1px solid #dce6ea;
  vertical-align: top;
}
td code, th code {
  white-space: normal;
  font-size: 0.82em;
  overflow-wrap: anywhere;
}
img {
  display: block;
  width: 100%;
  max-width: 100%;
  height: auto;
  margin: 0.12in auto 0.2in;
  break-inside: avoid;
  page-break-inside: avoid;
}
p:has(img) {
  margin: 0;
  break-inside: avoid;
  page-break-inside: avoid;
}
blockquote {
  margin: 0.16in 0;
  padding: 0.02in 0.16in;
  border-left: 4px solid #7aa6b4;
  color: #3c5160;
  background: #f6fafb;
}
hr { display: none; }
.source-artifacts li { font-size: 8.6pt; margin-bottom: 0.01in; overflow-wrap: anywhere; }
@media print {
  h1, h2, h3, table, img { break-inside: avoid; page-break-inside: avoid; }
  p, li { orphans: 3; widows: 3; }
}
"""


def render_html(markdown_path: Path, html_path: Path) -> None:
    source = markdown_path.read_text(encoding="utf-8")
    body = markdown(
        source,
        extensions=[
            "extra",
            "tables",
            "fenced_code",
            "toc",
            "sane_lists",
            "attr_list",
        ],
        output_format="html5",
    )
    body = body.replace('<h2 id="source-artifacts">Source Artifacts</h2>\n<ul>', '<h2 id="source-artifacts">Source Artifacts</h2>\n<ul class="source-artifacts">')
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Resume Tailoring Evidence-Grounded Case Study</title>
  <style>{CSS}</style>
</head>
<body>
  <main>{body}</main>
</body>
</html>
"""
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")


def render_pdf(html_path: Path, pdf_path: Path) -> None:
    script = f"""
const {{ chromium }} = require(process.cwd() + '/node_modules/@playwright/test');
(async () => {{
  const browser = await chromium.launch({{ headless: true }});
  const page = await browser.newPage({{ viewport: {{ width: 1100, height: 1500 }}, deviceScaleFactor: 1 }});
  await page.goto({json.dumps(html_path.resolve().as_uri())}, {{ waitUntil: 'networkidle' }});
  await page.emulateMedia({{ media: 'print' }});
  await page.pdf({{
    path: {json.dumps(str(pdf_path.resolve()))},
    format: 'Letter',
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: false
  }});
  await browser.close();
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
"""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        subprocess.run(
            ["node", str(script_path)],
            cwd=ROOT / "dashboardv2",
            check=True,
        )
    finally:
        script_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--html", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--html-only", action="store_true")
    args = parser.parse_args()

    markdown_path = args.input if args.input.is_absolute() else ROOT / args.input
    html_path = args.html if args.html.is_absolute() else ROOT / args.html
    pdf_path = args.pdf if args.pdf.is_absolute() else ROOT / args.pdf

    render_html(markdown_path, html_path)
    print(f"Wrote HTML: {html_path}")
    if not args.html_only:
        render_pdf(html_path, pdf_path)
        print(f"Wrote PDF: {pdf_path}")


if __name__ == "__main__":
    main()
