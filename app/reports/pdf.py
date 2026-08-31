"""Renders a completed Analysis as a branded PDF report.

Visual language (gradient top bar, teal section labels, bordered score
cards, logo+date footer) follows TEN Capital Network's existing report
template rather than the app's own dark-theme UI - this document is meant
to be printed/forwarded, so it uses a light, print-friendly palette.
"""

import io
import os
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.db import Analysis
from app.scoring.rubric import CATEGORIES

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "ten-capital-logo.webp")

TEXT = colors.HexColor("#12283f")
MUTED = colors.HexColor("#5b6b82")
TEAL = colors.HexColor("#1f9fb8")
CORAL = colors.HexColor("#f4645f")
AMBER = colors.HexColor("#f5a742")
BORDER = colors.HexColor("#dbe4ee")
TEAL_BG = colors.HexColor("#eaf6f9")
TRACK_BG = colors.HexColor("#eef2f7")

PAGE_SIZE = LETTER
MARGIN = 0.75 * inch
CONTENT_WIDTH = PAGE_SIZE[0] - 2 * MARGIN
TOP_BAR_HEIGHT = 7
_GRADIENT_FROM = (244, 100, 95)
_GRADIENT_TO = (245, 167, 66)


def _lerp_color(t: float) -> tuple[float, float, float]:
    r = _GRADIENT_FROM[0] + (_GRADIENT_TO[0] - _GRADIENT_FROM[0]) * t
    g = _GRADIENT_FROM[1] + (_GRADIENT_TO[1] - _GRADIENT_FROM[1]) * t
    b = _GRADIENT_FROM[2] + (_GRADIENT_TO[2] - _GRADIENT_FROM[2]) * t
    return r / 255, g / 255, b / 255


class _ScoreBar(Flowable):
    """A rounded horizontal score bar, filled left-to-right with the brand gradient."""

    def __init__(self, score: float, width: float, height: float = 8):
        super().__init__()
        self.score = max(0, min(100, score))
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        return self.width, self.height

    def draw(self):
        c = self.canv
        radius = self.height / 2

        c.saveState()
        c.setFillColor(TRACK_BG)
        c.roundRect(0, 0, self.width, self.height, radius, stroke=0, fill=1)
        c.restoreState()

        fill_width = self.width * (self.score / 100)
        if fill_width <= 0:
            return

        c.saveState()
        clip_path = c.beginPath()
        clip_path.roundRect(0, 0, self.width, self.height, radius)
        c.clipPath(clip_path, stroke=0)

        segments = 24
        for i in range(segments):
            t0 = i / segments
            t1 = (i + 1) / segments
            x0 = fill_width * t0
            x1 = fill_width * t1
            if x0 >= fill_width:
                break
            c.setFillColorRGB(*_lerp_color(t0))
            c.rect(x0, 0, (x1 - x0) + 0.75, self.height, stroke=0, fill=1)
        c.restoreState()


class _NumberedCanvas(pdfcanvas.Canvas):
    """Draws the gradient top bar and logo/page-number footer on every page,
    deferred to save() so the total page count is known for 'Page X/Y'."""

    def __init__(self, *args, **kwargs):
        pdfcanvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_decorations(total_pages)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def _draw_decorations(self, total_pages: int):
        width, height = PAGE_SIZE

        self.saveState()
        segments = 80
        for i in range(segments):
            t0 = i / segments
            t1 = (i + 1) / segments
            x0 = width * t0
            x1 = width * t1
            self.setFillColorRGB(*_lerp_color(t0))
            self.rect(x0, height - TOP_BAR_HEIGHT, (x1 - x0) + 0.75, TOP_BAR_HEIGHT, stroke=0, fill=1)
        self.restoreState()

        footer_y = 0.45 * inch
        self.saveState()
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.75)
        self.line(MARGIN, footer_y + 16, width - MARGIN, footer_y + 16)

        try:
            logo = ImageReader(_LOGO_PATH)
            logo_w, logo_h = logo.getSize()
            draw_h = 16
            draw_w = draw_h * (logo_w / logo_h)
            self.drawImage(
                logo, MARGIN, footer_y - 3, width=draw_w, height=draw_h,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

        self.setFont("Helvetica", 8)
        self.setFillColor(MUTED)
        self.drawCentredString(width / 2, footer_y, f"Page {self.getPageNumber()}/{total_pages}")
        self.drawRightString(
            width - MARGIN, footer_y, datetime.now(timezone.utc).strftime("%B %d, %Y")
        )
        self.restoreState()


_STYLES = {
    "eyebrow": ParagraphStyle(
        "eyebrow", fontName="Helvetica-Bold", fontSize=8.5, textColor=TEAL,
        spaceAfter=6, leading=11,
    ),
    "title": ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=21, textColor=TEXT,
        spaceAfter=14, leading=25,
    ),
    "section": ParagraphStyle(
        "section", fontName="Helvetica-Bold", fontSize=10, textColor=TEAL,
        spaceBefore=16, spaceAfter=8, leading=13, keepWithNext=True,
    ),
    "body": ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9.5, textColor=TEXT, leading=14,
    ),
    "muted": ParagraphStyle(
        "muted", fontName="Helvetica", fontSize=8.75, textColor=MUTED, leading=13,
    ),
    "score_headline": ParagraphStyle(
        "score_headline", fontName="Helvetica-Bold", fontSize=9, textColor=TEAL,
        leading=12,
    ),
    "cat_label": ParagraphStyle(
        "cat_label", fontName="Helvetica-Bold", fontSize=10, textColor=TEXT, leading=13,
    ),
    "cat_weight": ParagraphStyle(
        "cat_weight", fontName="Helvetica", fontSize=7.5, textColor=MUTED, leading=10,
    ),
    "cat_score": ParagraphStyle(
        "cat_score", fontName="Helvetica-Bold", fontSize=13, textColor=CORAL,
        alignment=2, leading=16,
    ),
}


def _esc(value: str) -> str:
    return (
        (value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _no_pad(style_overrides: dict | None = None) -> list:
    cmds = [
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]
    return cmds


def _overall_score_box(analysis: Analysis) -> Table:
    text = (
        f"<font color='#1f9fb8' size=8.5><b>OVERALL INVESTABILITY SCORE</b></font><br/>"
        f"<font color='#f4645f' size=30><b>{analysis.overall_score:g}</b></font>"
        f"<font color='#5b6b82' size=13>/100</font>"
    )
    para = Paragraph(text, ParagraphStyle("overall", fontName="Helvetica", leading=34))
    table = Table([[para]], colWidths=[CONTENT_WIDTH])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TEAL_BG),
        ("BOX", (0, 0), (-1, -1), 1, TEAL),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("LEFTPADDING", (0, 0), (-1, -1), 18),
        ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    return table


def _category_box(cat, cs: dict) -> Table:
    inner_width = CONTENT_WIDTH - 28

    label_para = Paragraph(
        f"{_esc(cat.label)}<br/><font size=7.5 color='#5b6b82'>WEIGHT {cat.weight}%</font>",
        _STYLES["cat_label"],
    )
    score_para = Paragraph(
        f"{cs['score']}<font size=9 color='#5b6b82'>/100</font>", _STYLES["cat_score"]
    )
    header = Table([[label_para, score_para]], colWidths=[inner_width * 0.78, inner_width * 0.22])
    header.setStyle(TableStyle(_no_pad() + [("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    bar = _ScoreBar(cs["score"], inner_width, height=8)
    justification = Paragraph(_esc(cs["justification"]), _STYLES["muted"])

    inner = Table(
        [[header], [Spacer(1, 6)], [bar], [Spacer(1, 7)], [justification]],
        colWidths=[inner_width],
    )
    inner.setStyle(TableStyle(_no_pad()))

    outer = Table([[inner]], colWidths=[CONTENT_WIDTH])
    outer.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return outer


def _bullet_list(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(_esc(item), _STYLES["body"]), spaceAfter=4) for item in items],
        bulletType="bullet",
        bulletColor=TEAL,
        bulletFontSize=9,
        leftIndent=14,
    )


def _numbered_list(items: list[str]) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(_esc(item), _STYLES["body"]), spaceAfter=6) for item in items],
        bulletType="1",
        bulletColor=TEAL,
        bulletFontName="Helvetica-Bold",
        leftIndent=16,
    )


def build_analysis_pdf(analysis: Analysis) -> bytes:
    """Renders `analysis` (must have status == 'complete') to PDF bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN + 0.15 * inch,
        bottomMargin=MARGIN,
        title=f"Investability Score - {analysis.filename}",
    )

    story = [
        Paragraph("TEN CAPITAL NETWORK &mdash; INVESTABILITY SCORE", _STYLES["eyebrow"]),
        Paragraph(_esc(analysis.filename), _STYLES["title"]),
        _overall_score_box(analysis),
        Spacer(1, 4),
    ]

    category_boxes = []
    for cat in CATEGORIES:
        cs = (analysis.category_scores or {}).get(cat.key)
        if not cs:
            continue
        category_boxes.append(_category_box(cat, cs))

    if category_boxes:
        header = Paragraph("CATEGORY BREAKDOWN", _STYLES["section"])
        story.append(KeepTogether([header, category_boxes[0]]))
        for box in category_boxes[1:]:
            story.append(Spacer(1, 8))
            story.append(box)

    if analysis.strengths:
        story.append(KeepTogether([
            Paragraph("STRENGTHS", _STYLES["section"]), _bullet_list(analysis.strengths)
        ]))

    if analysis.weaknesses:
        story.append(KeepTogether([
            Paragraph("WEAKNESSES", _STYLES["section"]), _bullet_list(analysis.weaknesses)
        ]))

    if analysis.action_items:
        story.append(KeepTogether([
            Paragraph("FIX THESE BEFORE YOU PITCH INVESTORS", _STYLES["section"]),
            _numbered_list(analysis.action_items),
        ]))

    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()
