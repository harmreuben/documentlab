"""Builds A4 PDF reports from simple HTML, using PyMuPDF (already used to read PDFs, so no new library).

Every value placed in a report goes through `esc` first, so text from a file or a person can't
change the report's layout.
"""
from __future__ import annotations

import html
import io
from datetime import datetime

import pymupdf

INK, MUTED, RULE = (0.06, 0.09, 0.16), (0.36, 0.40, 0.47), (0.86, 0.88, 0.91)
STATUS_COLOURS = {"PASS": "#0F8A5F", "FAIL": "#C2343B", "REVIEW_REQUIRED": "#A86200", "ERROR": "#0F172A"}
STATUS_WORDS = {"PASS": "Pass", "FAIL": "Fail", "REVIEW_REQUIRED": "Needs review", "NOT_SUPPORTED": "Not supported",
                "UNAVAILABLE": "Unavailable", "NOT_CHECKED": "Not checked", "ERROR": "Error"}

CSS = """
body { font-family: sans-serif; font-size: 9.5pt; color: #0F172A; line-height: 1.35; }
h1 { font-size: 17pt; margin: 0 0 4pt 0; }
h2 { font-size: 11.5pt; margin: 14pt 0 5pt 0; padding-bottom: 2pt; border-bottom: 0.5pt solid #D9DEE6; }
p { margin: 0 0 5pt 0; }
.muted { color: #5B6678; }
.small { font-size: 8pt; }
.banner { border: 0.8pt solid #C2343B; color: #C2343B; padding: 5pt; margin: 0 0 8pt 0; font-size: 8.5pt; }
.notice { border: 0.5pt solid #D9DEE6; background-color: #F4F6F9; padding: 5pt; margin: 6pt 0; font-size: 8.5pt; }
table { border-collapse: collapse; width: 100%; margin: 3pt 0 6pt 0; }
th { text-align: left; font-weight: bold; color: #5B6678; font-size: 8pt; padding: 3pt 4pt; border-bottom: 0.6pt solid #B8C0CC; }
td { padding: 3pt 4pt; border-bottom: 0.4pt solid #E3E7ED; vertical-align: top; }
.mono { font-family: monospace; font-size: 8.5pt; }
"""


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def status(value: str) -> str:
    colour = STATUS_COLOURS.get(value, "#5B6678")
    return f'<b style="color:{colour}">{esc(STATUS_WORDS.get(value, value))}</b>'


def table(headers: list[str], rows: list[list[str]], raw: bool = False) -> str:
    """rows are escaped unless raw=True (for cells built with esc()/status() already)."""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c if raw else esc(c)}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def facts(pairs: list[tuple[str, str]]) -> str:
    return "<table>" + "".join(f'<tr><td class="muted" width="26%">{esc(k)}</td><td>{esc(v)}</td></tr>'
                               for k, v in pairs) + "</table>"


def render(title: str, body: str, *, subtitle: str = "", banner: str = "", footer_note: str = "") -> bytes:
    """Lay the HTML out over as many A4 pages as needed, then add a footer to each page."""
    head = f'<h1>{esc(title)}</h1>' + (f'<p class="muted">{esc(subtitle)}</p>' if subtitle else "")
    story = pymupdf.Story(html=(f'<div class="banner">{esc(banner)}</div>' if banner else "") + head + body, user_css=CSS)
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    page_box = pymupdf.paper_rect("a4")
    content = page_box + (48, 52, -48, -56)
    more = True
    while more:
        device = writer.begin_page(page_box)
        more, _ = story.place(content)
        story.draw(device)
        writer.end_page()
    writer.close()

    doc = pymupdf.open(stream=out.getvalue(), filetype="pdf")
    stamp = datetime.now().strftime("%d %b %Y %H:%M")
    left = f"DocumentLab · {title}" + (f" · {footer_note}" if footer_note else "")
    for number, page in enumerate(doc, start=1):
        y = page.rect.height - 30
        page.draw_line((48, y - 8), (page.rect.width - 48, y - 8), color=RULE, width=0.5)
        page.insert_text((48, y + 4), left[:110], fontsize=7, color=MUTED)
        right = f"Generated {stamp} · Page {number} of {doc.page_count}"
        page.insert_text((page.rect.width - 48 - pymupdf.get_text_length(right, fontsize=7), y + 4), right,
                         fontsize=7, color=MUTED)
    doc.set_metadata({"title": title, "producer": "DocumentLab", "creator": "DocumentLab"})
    return doc.tobytes(garbage=3, deflate=True)
