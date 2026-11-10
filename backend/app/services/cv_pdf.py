"""Render a generated CV as a styled PDF.

The CV agent returns Markdown, so this module is a deliberately small
Markdown-to-PDF renderer for the shapes that agent produces: a name, a contact
line, `##` sections, `###` roles, italic date lines and bullets. That means the
PDF also works for AI-written CVs without a second generation call, so what the
student downloads is exactly what they previewed.

Fonts: reportlab bundles the Bitstream Vera family, which covers Latin, Greek and
Cyrillic. It is registered as the document font so accents and typographic
punctuation survive; if registration fails we fall back to Helvetica.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate

INK = colors.HexColor("#111827")
BODY = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#64748b")
ACCENT = colors.HexColor("#4338ca")
RULE = colors.HexColor("#dbe0ea")

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"

_BULLET = "•"


def _register_fonts() -> None:
    """Register a Unicode-capable font family once, falling back to Helvetica."""
    global FONT, FONT_BOLD, FONT_ITALIC
    if FONT != "Helvetica":
        return

    fonts_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    if not fonts_dir.exists():  # pragma: no cover - packaging oddity
        return

    try:
        pdfmetrics.registerFont(TTFont("CVFont", str(fonts_dir / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("CVFont-Bold", str(fonts_dir / "VeraBd.ttf")))
        pdfmetrics.registerFont(TTFont("CVFont-Italic", str(fonts_dir / "VeraIt.ttf")))
        pdfmetrics.registerFont(TTFont("CVFont-BoldItalic", str(fonts_dir / "VeraBI.ttf")))
        pdfmetrics.registerFontFamily(
            "CVFont",
            normal="CVFont",
            bold="CVFont-Bold",
            italic="CVFont-Italic",
            boldItalic="CVFont-BoldItalic",
        )
    except Exception:  # pragma: no cover - keep PDFs working regardless
        return

    FONT, FONT_BOLD, FONT_ITALIC = "CVFont", "CVFont-Bold", "CVFont-Italic"


def _inline(value: str) -> str:
    """Escape XML and turn the agent's **bold** / _italic_ marks into markup."""
    text = escape(value.strip())
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w/])_([^_\n]+)_(?![\w/])", r"<i>\1</i>", text)
    text = text.replace("`", "")
    return text


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "cv-body",
        fontName=FONT,
        fontSize=9.6,
        leading=13.8,
        textColor=BODY,
        alignment=TA_LEFT,
        spaceAfter=3,
    )
    return {
        "name": ParagraphStyle(
            "cv-name", parent=base, fontName=FONT_BOLD, fontSize=23, leading=26, textColor=INK
        ),
        "contact": ParagraphStyle(
            "cv-contact", parent=base, fontSize=8.8, leading=12, textColor=MUTED, spaceBefore=5, spaceAfter=7
        ),
        "section": ParagraphStyle(
            "cv-section",
            parent=base,
            fontName=FONT_BOLD,
            fontSize=9,
            leading=11,
            textColor=ACCENT,
            spaceBefore=12,
            spaceAfter=3,
        ),
        "role": ParagraphStyle(
            "cv-role", parent=base, fontName=FONT_BOLD, fontSize=10.4, leading=13, textColor=INK, spaceBefore=5, spaceAfter=1
        ),
        "dates": ParagraphStyle(
            "cv-dates", parent=base, fontName=FONT_ITALIC, fontSize=8.5, leading=11, textColor=MUTED, spaceAfter=2
        ),
        "bullet": ParagraphStyle(
            "cv-bullet", parent=base, leftIndent=11, bulletIndent=1, spaceAfter=2, leading=13.2
        ),
        "body": base,
    }


def _is_contact(line: str) -> bool:
    return "@" in line or "·" in line or bool(re.search(r"\+?\d[\d\s()-]{6,}", line))


def _story(markdown: str, styles: dict[str, ParagraphStyle]) -> list:
    """Turn the CV markdown into reportlab flowables."""
    story: list = []
    paragraph: list[str] = []
    seen_section = False

    def flush() -> None:
        if not paragraph:
            return
        text = " ".join(part.strip() for part in paragraph if part.strip())
        paragraph.clear()
        if not text:
            return
        style = styles["contact"] if (not seen_section and _is_contact(text)) else styles["body"]
        story.append(Paragraph(_inline(text), style))

    for raw in markdown.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush()
            continue

        if stripped.startswith("# ") and not story:
            flush()
            story.append(Paragraph(_inline(stripped[2:]), styles["name"]))
            continue

        if stripped.startswith("## "):
            flush()
            seen_section = True
            title = stripped[3:].strip().rstrip(":").upper()
            story.append(Paragraph(_inline(title), styles["section"]))
            story.append(HRFlowable(width="100%", thickness=0.7, color=RULE, spaceBefore=0, spaceAfter=5))
            continue

        if stripped.startswith("### "):
            flush()
            seen_section = True
            story.append(Paragraph(_inline(stripped[4:]), styles["role"]))
            continue

        if re.fullmatch(r"[_*]{1,2}[^_*].*?[_*]{1,2}", stripped) and len(stripped) < 120:
            flush()
            story.append(Paragraph(_inline(stripped.strip("_*")), styles["dates"]))
            continue

        if re.match(r"^[-*]\s+", stripped):
            flush()
            # Keep bullets together with the role line above them.
            bullet = Paragraph(_inline(stripped[2:]), styles["bullet"], bulletText=_BULLET)
            story.append(bullet)
            continue

        paragraph.append(stripped)

    flush()
    return story


def render_cv_pdf(markdown: str, *, full_name: str | None = None) -> bytes:
    """Return a one-column, ATS-friendly A4 PDF for ``markdown``."""
    _register_fonts()
    styles = _styles()
    story = _story(markdown, styles)
    if not story:
        raise ValueError("Nothing to render")

    buffer = io.BytesIO()
    title_name = (full_name or "").strip() or "CV"
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=17 * mm,
        title=f"{title_name} - CV",
        author=title_name,
        subject="Curriculum Vitae",
        creator="Study Companion",
    )

    def footer(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, title_name)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
