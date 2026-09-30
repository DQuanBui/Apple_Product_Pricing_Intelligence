"""Render reports/final_report.md to a styled PDF (reports/final_report.pdf).

Converts the Markdown to HTML and prints it with a headless Chromium browser
(Microsoft Edge or Google Chrome), so the PDF matches the Markdown exactly.

    pip install markdown
    python reports/build_report.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

import markdown

REPORT_DIR = Path(__file__).resolve().parent
SOURCE = REPORT_DIR / "final_report.md"
HTML_OUT = REPORT_DIR / "final_report.html"
PDF_OUT = REPORT_DIR / "final_report.pdf"

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "msedge",
]

CSS = """
@page { size: Letter; margin: 16mm 16mm 18mm 16mm; }
:root { --ink: #0b0b0b; --ink-2: #3d3c39; --muted: #6b6a65; --rule: #e1e0d9; --accent: #2a78d6; --wash: #f5f5f2; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; color: var(--ink-2); font-size: 10.5pt; line-height: 1.5; margin: 0; }
h1 { color: var(--ink); font-size: 24pt; line-height: 1.15; margin: 0 0 8pt; letter-spacing: -0.01em; }
h1 + p { color: var(--muted); margin-top: 0; }
h2 { color: var(--ink); font-size: 15pt; margin: 22pt 0 8pt; padding-bottom: 4pt; border-bottom: 1.5pt solid var(--accent); break-after: avoid; }
h3 { color: var(--ink); font-size: 12pt; margin: 16pt 0 6pt; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
a { color: var(--accent); text-decoration: none; }
strong { color: var(--ink); }
hr { border: 0; border-top: 1pt solid var(--rule); margin: 12pt 0; }
table { width: 100%; border-collapse: collapse; margin: 8pt 0 12pt; font-size: 9pt; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th { text-align: left; color: var(--ink); background: var(--wash); font-weight: 600; }
th, td { padding: 4pt 6pt; border-bottom: 0.75pt solid var(--rule); vertical-align: top; }
img { max-width: 100%; display: block; margin: 8pt auto 4pt; break-inside: avoid; }
p:has(> img) { break-inside: avoid; margin: 0; }
p > em:only-child { display: block; color: var(--muted); font-size: 9pt; margin-bottom: 8pt; }
code { font-family: Consolas, "SF Mono", monospace; font-size: 8.8pt; background: var(--wash); padding: 0 3pt; border-radius: 3pt; }
pre { background: var(--wash); padding: 8pt 10pt; border-radius: 6pt; font-size: 8.5pt; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; }
ul, ol { padding-left: 18pt; }
"""


def find_browser() -> str:
    for candidate in BROWSERS:
        path = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if path:
            return path
    sys.exit("No Edge or Chrome installation found to print the PDF.")


def main() -> None:
    body = markdown.markdown(SOURCE.read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "sane_lists"])
    HTML_OUT.write_text(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>Apple Product Pricing Intelligence - Final Report</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>",
        encoding="utf-8",
    )
    subprocess.run(
        [
            find_browser(),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={PDF_OUT}",
            HTML_OUT.as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    HTML_OUT.unlink()
    print(f"Wrote {PDF_OUT}")


if __name__ == "__main__":
    main()
