"""
Deliverable generation: turns agent output (plain text/structured data) into
real downloadable DOCX / PPTX / XLSX files, saved under a per-task output dir.
"""
from __future__ import annotations
import uuid
from pathlib import Path

from docx import Document
from docx.shared import Pt
from pptx import Presentation
from pptx.util import Inches, Pt as PptPt
from openpyxl import Workbook

OUTPUT_DIR = Path("/data/generated")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _new_path(prefix: str, ext: str) -> Path:
    return OUTPUT_DIR / f"{prefix}-{uuid.uuid4().hex[:8]}.{ext}"


def generate_docx(title: str, body_text: str, sections: list[dict] | None = None) -> Path:
    """sections: [{'heading': str, 'text': str}] for a multi-section report/approval note."""
    doc = Document()
    doc.add_heading(title, level=1)

    if sections:
        for section in sections:
            doc.add_heading(section["heading"], level=2)
            for para in section["text"].split("\n\n"):
                doc.add_paragraph(para)
    else:
        for para in body_text.split("\n\n"):
            doc.add_paragraph(para)

    path = _new_path("document", "docx")
    doc.save(path)
    return path


def generate_approval_note(title: str, observations: str, recommendation: str,
                            references: list[str]) -> Path:
    doc = Document()
    doc.add_heading(title, level=1)
    doc.add_heading("Observations", level=2)
    doc.add_paragraph(observations)
    doc.add_heading("Recommendation", level=2)
    doc.add_paragraph(recommendation)
    if references:
        doc.add_heading("References", level=2)
        for ref in references:
            doc.add_paragraph(ref, style="List Bullet")
    doc.add_paragraph()
    p = doc.add_paragraph("Prepared by: ")
    p.add_run("_____________________     ").bold = False
    doc.add_paragraph("Approved by: _____________________")
    path = _new_path("approval-note", "docx")
    doc.save(path)
    return path


def generate_pptx(title: str, slides: list[dict]) -> Path:
    """slides: [{'title': str, 'bullets': [str, ...]}]"""
    prs = Presentation()
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    slide.shapes.title.text = title

    bullet_layout = prs.slide_layouts[1]
    for s in slides:
        slide = prs.slides.add_slide(bullet_layout)
        slide.shapes.title.text = s["title"]
        body = slide.placeholders[1].text_frame
        body.clear()
        for i, bullet in enumerate(s["bullets"]):
            p = body.paragraphs[0] if i == 0 else body.add_paragraph()
            p.text = bullet
            p.font.size = PptPt(18)

    path = _new_path("presentation", "pptx")
    prs.save(path)
    return path


def generate_xlsx(title: str, headers: list[str], rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]  # Excel sheet name limit
    ws.append(headers)
    for row in rows:
        ws.append(row)

    # basic auto-width
    for col_idx, header in enumerate(headers, start=1):
        col_letter = ws.cell(row=1, column=col_idx).column_letter
        max_len = max([len(str(header))] + [len(str(r[col_idx - 1])) for r in rows if len(r) >= col_idx])
        ws.column_dimensions[col_letter].width = max_len + 2

    path = _new_path("spreadsheet", "xlsx")
    wb.save(path)
    return path
