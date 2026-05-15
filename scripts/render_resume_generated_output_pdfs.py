#!/usr/bin/env python3
"""Render generated resume-output markdown artifacts to clean PDF companions."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from markdown import markdown


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "docs/ai-artifacts/resume-tailoring-generated-resumes"


@dataclass(frozen=True)
class ResumeArtifact:
    stem: str
    title: str


ARTIFACTS = [
    ResumeArtifact("draftkings-analyst-i-lazy", "DraftKings Analyst I - Lazy Prompt"),
    ResumeArtifact("draftkings-analyst-i-engineered", "DraftKings Analyst I - Engineered Prompt"),
    ResumeArtifact("anthropic-marketing-near-miss-lazy", "Anthropic Marketing Near-Miss - Lazy Prompt"),
    ResumeArtifact("anthropic-marketing-near-miss-engineered", "Anthropic Marketing Near-Miss - Engineered Prompt"),
]


CSS = """
:root {
  color: #17212b;
  background: #ffffff;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 10.6pt;
  line-height: 1.43;
}
@page { size: Letter; margin: 0.55in 0.62in 0.58in 0.62in; }
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #ffffff;
  color: #17212b;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
main { max-width: 7.5in; margin: 0 auto; }
.artifact-title {
  margin: 0 0 0.18in;
  padding-bottom: 0.09in;
  border-bottom: 1.2px solid #cfdce4;
  color: #5b6c7c;
  font-size: 9.2pt;
  font-weight: 720;
  letter-spacing: 0.055em;
  text-transform: uppercase;
}
h1 {
  margin: 0 0 0.14in;
  color: #0f2537;
  font-size: 20pt;
  line-height: 1.1;
  letter-spacing: 0;
  font-weight: 780;
}
h2, h3 {
  margin: 0.18in 0 0.065in;
  color: #102838;
  font-size: 11.2pt;
  line-height: 1.2;
  font-weight: 760;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  break-after: avoid;
  page-break-after: avoid;
}
p { margin: 0 0 0.07in; }
ul, ol { margin: 0.02in 0 0.12in 0.21in; padding-left: 0.18in; }
li { margin: 0.018in 0; }
strong { font-weight: 760; color: #111d28; }
em { color: #34495a; }
a { color: #0d5f73; text-decoration: none; }
hr {
  border: 0;
  border-top: 1px solid #dce6eb;
  margin: 0.14in 0;
}
code {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.9em;
  color: #17324d;
  background: #eef4f7;
  border: 1px solid #d9e5ea;
  border-radius: 4px;
  padding: 0.01in 0.035in;
}
blockquote {
  margin: 0.12in 0;
  padding: 0.02in 0.14in;
  border-left: 4px solid #7aa6b4;
  color: #3c5160;
  background: #f6fafb;
}
@media print {
  h1, h2, h3 { break-after: avoid; page-break-after: avoid; }
  p, li { orphans: 3; widows: 3; }
}
"""


def render_html(markdown_path: Path, html_path: Path, title: str) -> None:
    body = markdown(
        markdown_path.read_text(encoding="utf-8"),
        extensions=["extra", "tables", "fenced_code", "sane_lists"],
        output_format="html5",
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>{CSS}</style>
</head>
<body>
  <main>
    <div class="artifact-title">{title}</div>
    {body}
  </main>
</body>
</html>
"""
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
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", delete=False) as handle:
        handle.write(script)
        script_path = Path(handle.name)
    try:
        subprocess.run(["node", str(script_path)], cwd=ROOT / "dashboardv2", check=True)
    finally:
        script_path.unlink(missing_ok=True)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for artifact in ARTIFACTS:
        markdown_path = OUTPUT_DIR / f"{artifact.stem}.md"
        html_path = OUTPUT_DIR / f"{artifact.stem}.html"
        pdf_path = OUTPUT_DIR / f"{artifact.stem}.pdf"
        render_html(markdown_path, html_path, artifact.title)
        render_pdf(html_path, pdf_path)
        print(f"Wrote {pdf_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
