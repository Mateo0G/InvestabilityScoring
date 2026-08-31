"""Renders a completed Analysis as a branded .docx report.

Mirrors app/reports/pdf.py's visual language (gradient top bar, teal
section labels, bordered score cards with a gradient bar, logo+date
footer) using python-docx primitives - tables standing in for boxes/bars
since Word has no native rounded-rect or gradient-fill support.
"""

import io
import os
from datetime import datetime, timezone

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from app.models.db import Analysis
from app.scoring.rubric import CATEGORIES

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "ten-capital-logo.png")
_FONT = "Arial"

TEXT = "12283F"
MUTED = "5B6B82"
TEAL = "1F9FB8"
CORAL = "F4645F"
AMBER = "F5A742"
BORDER = "DBE4EE"
TEAL_BG = "EAF6F9"
TRACK_BG = "EEF2F7"

_GRADIENT_FROM = (0xF4, 0x64, 0x5F)
_GRADIENT_TO = (0xF5, 0xA7, 0x42)

PAGE_WIDTH_IN = 8.5
PAGE_HEIGHT_IN = 11.0
MARGIN_IN = 0.75
CONTENT_WIDTH_IN = PAGE_WIDTH_IN - 2 * MARGIN_IN


def _lerp_hex(t: float) -> str:
    t = max(0.0, min(1.0, t))
    r = round(_GRADIENT_FROM[0] + (_GRADIENT_TO[0] - _GRADIENT_FROM[0]) * t)
    g = round(_GRADIENT_FROM[1] + (_GRADIENT_TO[1] - _GRADIENT_FROM[1]) * t)
    b = round(_GRADIENT_FROM[2] + (_GRADIENT_TO[2] - _GRADIENT_FROM[2]) * t)
    return f"{r:02X}{g:02X}{b:02X}"


# ---- low-level oxml helpers (python-docx has no high-level API for these) ----

def _set_cell_background(cell, color_hex: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tcPr.append(shd)


def _set_cell_border(cell, color_hex: str = BORDER, sz: int = 6, edges=("top", "left", "bottom", "right")):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in edges:
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color_hex)
        borders.append(el)
    tcPr.append(borders)


def _set_cell_margins(cell, top=80, bottom=80, left=100, right=100):
    tcPr = cell._tc.get_or_add_tcPr()
    mar = OxmlElement("w:tcMar")
    for edge, value in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:w"), str(value))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tcPr.append(mar)


def _set_table_fixed_layout(table, width_in: float):
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(int(width_in * 1440)))
    tbl_pr.append(tblW)


def _set_col_widths(table, widths_in: list[float]):
    for i, w in enumerate(widths_in):
        table.columns[i].width = Inches(w)
    for row in table.rows:
        for cell, w in zip(row.cells, widths_in):
            cell.width = Inches(w)


def _set_row_height(row, height_in: float, exact: bool = True):
    trPr = row._tr.get_or_add_trPr()
    trHeight = OxmlElement("w:trHeight")
    trHeight.set(qn("w:val"), str(int(height_in * 1440)))
    trHeight.set(qn("w:hRule"), "exact" if exact else "atLeast")
    trPr.append(trHeight)


def _no_borders(cell):
    _set_cell_border(cell, color_hex="FFFFFF", sz=0)
    tcPr = cell._tc.get_or_add_tcPr()
    # remove any existing tcBorders duplicate to avoid two <w:tcBorders>
    for el in tcPr.findall(qn("w:tcBorders")):
        pass


def _clear_paragraph(paragraph):
    paragraph.text = ""
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)


def _add_run(paragraph, text, size=10, color=TEXT, bold=False, italic=False):
    run = paragraph.add_run(text)
    run.font.name = _FONT
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    run.font.bold = bold
    run.font.italic = italic
    return run


def _paragraph(container, text="", size=10, color=TEXT, bold=False,
               space_before=0, space_after=0, align=None):
    para = container.add_paragraph()
    para.paragraph_format.space_before = Pt(space_before)
    para.paragraph_format.space_after = Pt(space_after)
    if align is not None:
        para.alignment = align
    if text:
        _add_run(para, text, size=size, color=color, bold=bold)
    return para


def _add_field(paragraph, instr: str, cached_text: str = "1"):
    def _r():
        return paragraph.add_run()._r

    begin = _r()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    begin.append(fld_begin)

    instr_run = _r()
    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = instr
    instr_run.append(instr_el)

    sep = _r()
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    sep.append(fld_sep)

    cached_run = paragraph.add_run(cached_text)
    cached_run.font.name = _FONT
    cached_run.font.size = Pt(8.5)
    cached_run.font.color.rgb = RGBColor.from_string(MUTED)

    end = _r()
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    end.append(fld_end)


# ---- page decorations ----

def _build_header(header):
    for p in header.paragraphs:
        _clear_paragraph(p)

    segments = 24
    table = header.add_table(rows=1, cols=segments, width=Inches(CONTENT_WIDTH_IN))
    table.alignment = WD_ALIGN_VERTICAL.CENTER
    _set_table_fixed_layout(table, CONTENT_WIDTH_IN)
    seg_width = CONTENT_WIDTH_IN / segments
    _set_col_widths(table, [seg_width] * segments)
    _set_row_height(table.rows[0], 0.09)

    for i, cell in enumerate(table.rows[0].cells):
        t = i / (segments - 1)
        _set_cell_background(cell, _lerp_hex(t))
        _set_cell_margins(cell, top=0, bottom=0, left=0, right=0)
        _clear_paragraph(cell.paragraphs[0])


def _build_footer(footer):
    for p in footer.paragraphs:
        _clear_paragraph(p)

    table = footer.add_table(rows=1, cols=3, width=Inches(CONTENT_WIDTH_IN))
    _set_table_fixed_layout(table, CONTENT_WIDTH_IN)
    _set_col_widths(table, [CONTENT_WIDTH_IN * 0.34, CONTENT_WIDTH_IN * 0.32, CONTENT_WIDTH_IN * 0.34])

    logo_cell, center_cell, right_cell = table.rows[0].cells
    for cell in (logo_cell, center_cell, right_cell):
        _set_cell_border(cell, color_hex=BORDER, sz=4, edges=("top",))
        _set_cell_margins(cell, top=60, bottom=0, left=0, right=0)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    logo_p = logo_cell.paragraphs[0]
    logo_p.paragraph_format.space_before = Pt(0)
    logo_p.paragraph_format.space_after = Pt(0)
    try:
        run = logo_p.add_run()
        run.add_picture(_LOGO_PATH, height=Inches(0.18))
    except Exception:
        _add_run(logo_p, "TEN CAPITAL NETWORK", size=7, color=MUTED, bold=True)

    center_p = center_cell.paragraphs[0]
    center_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    center_p.paragraph_format.space_before = Pt(0)
    center_p.paragraph_format.space_after = Pt(0)
    _add_run(center_p, "Page ", size=8.5, color=MUTED)
    _add_field(center_p, "PAGE", "1")
    _add_run(center_p, " of ", size=8.5, color=MUTED)
    _add_field(center_p, "NUMPAGES", "1")

    right_p = right_cell.paragraphs[0]
    right_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    right_p.paragraph_format.space_before = Pt(0)
    right_p.paragraph_format.space_after = Pt(0)
    _add_run(right_p, datetime.now(timezone.utc).strftime("%B %d, %Y"), size=8.5, color=MUTED)


# ---- body content ----

def _overall_score_box(doc, analysis: Analysis):
    table = doc.add_table(rows=1, cols=1)
    _set_table_fixed_layout(table, CONTENT_WIDTH_IN)
    _set_col_widths(table, [CONTENT_WIDTH_IN])
    cell = table.rows[0].cells[0]
    _set_cell_background(cell, TEAL_BG)
    _set_cell_border(cell, color_hex=TEAL, sz=10)
    _set_cell_margins(cell, top=180, bottom=180, left=260, right=260)

    eyebrow = cell.paragraphs[0]
    eyebrow.paragraph_format.space_after = Pt(4)
    _add_run(eyebrow, "OVERALL INVESTABILITY SCORE", size=8.5, color=TEAL, bold=True)

    score_p = cell.add_paragraph()
    score_p.paragraph_format.space_before = Pt(2)
    _add_run(score_p, f"{analysis.overall_score:g}", size=30, color=CORAL, bold=True)
    _add_run(score_p, "/100", size=13, color=MUTED)

    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def _score_bar(container, score: float, width_in: float):
    table = container.add_table(rows=1, cols=2)
    _set_table_fixed_layout(table, width_in)
    filled = width_in * max(0, min(100, score)) / 100
    track = max(width_in - filled, 0.01)
    if filled <= 0.01:
        filled, track = 0.01, width_in - 0.01
    _set_col_widths(table, [filled, track])
    _set_row_height(table.rows[0], 0.11)

    fill_cell, track_cell = table.rows[0].cells
    _set_cell_background(fill_cell, _lerp_hex(score / 100))
    _set_cell_background(track_cell, TRACK_BG)
    for c in (fill_cell, track_cell):
        _set_cell_margins(c, top=0, bottom=0, left=0, right=0)
        _clear_paragraph(c.paragraphs[0])
    return table


def _category_box(doc, cat, cs: dict):
    inner_width = CONTENT_WIDTH_IN - 0.3

    outer = doc.add_table(rows=1, cols=1)
    _set_table_fixed_layout(outer, CONTENT_WIDTH_IN)
    _set_col_widths(outer, [CONTENT_WIDTH_IN])
    outer_cell = outer.rows[0].cells[0]
    _set_cell_background(outer_cell, "FFFFFF")
    _set_cell_border(outer_cell, color_hex=BORDER, sz=6)
    _set_cell_margins(outer_cell, top=160, bottom=160, left=150, right=150)
    _clear_paragraph(outer_cell.paragraphs[0])

    header = outer_cell.add_table(rows=1, cols=2)
    _set_table_fixed_layout(header, inner_width)
    _set_col_widths(header, [inner_width * 0.76, inner_width * 0.24])
    label_cell, score_cell = header.rows[0].cells
    for c in (label_cell, score_cell):
        _set_cell_margins(c, top=0, bottom=0, left=0, right=0)
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    label_p = label_cell.paragraphs[0]
    _add_run(label_p, cat.label, size=10.5, color=TEXT, bold=True)
    weight_p = label_cell.add_paragraph()
    weight_p.paragraph_format.space_before = Pt(0)
    _add_run(weight_p, f"WEIGHT {cat.weight}%", size=7.5, color=MUTED, bold=False)

    score_p = score_cell.paragraphs[0]
    score_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_run(score_p, f"{cs['score']}", size=14, color=CORAL, bold=True)
    _add_run(score_p, "/100", size=9, color=MUTED)

    bar_holder = outer_cell.add_paragraph()
    bar_holder.paragraph_format.space_before = Pt(6)
    bar_holder.paragraph_format.space_after = Pt(6)
    _score_bar(outer_cell, cs["score"], inner_width)

    just_p = outer_cell.add_paragraph()
    just_p.paragraph_format.space_before = Pt(6)
    _add_run(just_p, cs["justification"], size=9.25, color=MUTED)

    return outer


def _section_header(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.keep_with_next = True
    _add_run(p, text.upper(), size=10.5, color=TEAL, bold=True)
    return p


def _bullet_list(doc, items: list[str]):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(4)
        _add_run(p, item, size=9.5, color=TEXT)


def _numbered_list(doc, items: list[str]):
    for item in items:
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.space_after = Pt(6)
        _add_run(p, item, size=9.5, color=TEXT)


def build_analysis_docx(analysis: Analysis) -> bytes:
    """Renders `analysis` (must have status == 'complete') to .docx bytes."""
    doc = Document()

    normal = doc.styles["Normal"]
    normal.font.name = _FONT
    normal.font.size = Pt(10)
    normal.font.color.rgb = RGBColor.from_string(TEXT)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)

    section = doc.sections[0]
    section.page_width = Inches(PAGE_WIDTH_IN)
    section.page_height = Inches(PAGE_HEIGHT_IN)
    section.left_margin = Inches(MARGIN_IN)
    section.right_margin = Inches(MARGIN_IN)
    section.top_margin = Inches(MARGIN_IN + 0.15)
    section.bottom_margin = Inches(MARGIN_IN)
    section.header_distance = Inches(0.35)
    section.footer_distance = Inches(0.4)

    _build_header(section.header)
    _build_footer(section.footer)

    eyebrow = doc.add_paragraph()
    eyebrow.paragraph_format.space_after = Pt(4)
    _add_run(eyebrow, "TEN CAPITAL NETWORK — INVESTABILITY SCORE", size=8.5, color=TEAL, bold=True)

    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(12)
    _add_run(title, analysis.filename, size=20, color=TEXT, bold=True)

    _overall_score_box(doc, analysis)

    category_items = []
    for cat in CATEGORIES:
        cs = (analysis.category_scores or {}).get(cat.key)
        if cs:
            category_items.append((cat, cs))

    if category_items:
        _section_header(doc, "Category Breakdown")
        for cat, cs in category_items:
            _category_box(doc, cat, cs)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)

    if analysis.strengths:
        _section_header(doc, "Strengths")
        _bullet_list(doc, analysis.strengths)

    if analysis.weaknesses:
        _section_header(doc, "Weaknesses")
        _bullet_list(doc, analysis.weaknesses)

    if analysis.action_items:
        _section_header(doc, "Fix These Before You Pitch Investors")
        _numbered_list(doc, analysis.action_items)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
