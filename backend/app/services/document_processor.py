"""Document extraction and chunking.

Parsers are imported lazily and guarded so the API keeps working (with a clear
warning on the document) if an optional dependency is not installed.
"""

from __future__ import annotations

import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from ..utils.text import clean_text, split_sentences, words
from . import ocr

#: Below this many words a PDF is treated as scanned and sent through OCR.
MIN_PDF_TEXT_WORDS = 25

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text", ".rst", ".csv", ".json", ".log"}
HTML_EXTENSIONS = {".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
SLIDE_EXTENSIONS = {".pptx"}
DOC_EXTENSIONS = {".docx"}


class ExtractionError(Exception):
    """Raised when a document cannot be turned into usable text."""


@dataclass
class ExtractionResult:
    text: str
    page_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(words(self.text))


def _read_plain(path: Path) -> ExtractionResult:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return ExtractionResult(text=raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise ExtractionError("File is not valid UTF-8 or Latin-1 text")


def _read_pdf(
    path: Path,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> ExtractionResult:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ExtractionError("PDF support is not installed (pip install pypdf)") from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001 - pypdf raises many types
        raise ExtractionError(f"Could not read PDF: {exc}") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError("PDF is password protected") from exc

    parts: list[str] = []
    warnings: list[str] = []
    pages = list(reader.pages)
    for index, page in enumerate(pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - a broken page should not kill the upload
            warnings.append(f"Page {index} could not be read")
            continue
        if text.strip():
            parts.append(text.strip())

    text = "\n\n".join(parts)

    # A scan carries no text layer, so fall back to OCR when the extracted text
    # is too thin to build topics from.
    if len(words(text)) < MIN_PDF_TEXT_WORDS:
        settings = get_settings()
        if not settings.ocr_enabled:
            warnings.append(
                "No selectable text found - this looks like a scanned PDF and OCR is disabled."
            )
        else:
            # Announce OCR before the first page so the UI can show page progress
            # instead of sitting on "reading" for the whole scan.
            if on_progress is not None:
                on_progress("ocr", 0, min(len(pages), settings.ocr_max_pages))
            ocr_text, ocr_warnings, _ = ocr.ocr_pdf(
                path,
                max_pages=settings.ocr_max_pages,
                dpi=settings.ocr_dpi,
                page_total=len(pages),
                on_page=(
                    (lambda done, total: on_progress("ocr", done, total))
                    if on_progress is not None
                    else None
                ),
            )
            warnings.extend(ocr_warnings)
            if ocr_text:
                text = ocr_text if not text.strip() else f"{text}\n\n{ocr_text}"

    return ExtractionResult(text=text, page_count=len(pages), warnings=warnings)


def _read_docx(path: Path) -> ExtractionResult:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("DOCX support is not installed (pip install python-docx)") from exc

    try:
        document = docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"Could not read DOCX: {exc}") from exc

    blocks: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower() if paragraph.style else ""
        if style.startswith("heading") or style == "title":
            blocks.append(f"\n\n{text}\n")
        else:
            blocks.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                blocks.append(" | ".join(cells))

    return ExtractionResult(text="\n".join(blocks), page_count=0)


def _read_pptx(path: Path) -> ExtractionResult:
    try:
        from pptx import Presentation
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError("PPTX support is not installed (pip install python-pptx)") from exc

    try:
        presentation = Presentation(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"Could not read PPTX: {exc}") from exc

    slides: list[str] = []
    for number, slide in enumerate(presentation.slides, start=1):
        lines: list[str] = []
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            for paragraph in shape.text_frame.paragraphs:
                text = "".join(run.text for run in paragraph.runs).strip()
                if text:
                    lines.append(text)
        if lines:
            slides.append(f"Slide {number}\n" + "\n".join(lines))

    return ExtractionResult(text="\n\n".join(slides), page_count=len(presentation.slides))


def _read_html(path: Path) -> ExtractionResult:
    raw = _read_plain(path).text
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return ExtractionResult(text=text)


def _read_image(path: Path) -> ExtractionResult:
    settings = get_settings()
    if not settings.ocr_enabled:
        return ExtractionResult(
            text="",
            warnings=["OCR is disabled, so this image could not be read as text."],
        )
    try:
        from PIL import Image

        with Image.open(str(path)) as image:
            text = ocr.ocr_image(image.convert("RGB"))
    except Exception as exc:  # noqa: BLE001 - OCR is optional
        return ExtractionResult(text="", warnings=[f"Could not read image: {exc}"])

    engine = ocr.engine_name()
    if not text.strip():
        if engine is None:
            return ExtractionResult(
                text="",
                warnings=[
                    "No OCR engine is installed, so this image was not read. "
                    "Install one with: pip install rapidocr-onnxruntime"
                ],
            )
        return ExtractionResult(
            text="",
            warnings=[f"OCR ({engine}) found no readable text in this image."],
        )
    return ExtractionResult(
        text=text,
        warnings=[f"Text recovered from image with OCR ({engine})."],
    )


class DocumentProcessor:
    """Turns an uploaded file into clean text."""

    SUPPORTED_EXTENSIONS = sorted(
        TEXT_EXTENSIONS
        | HTML_EXTENSIONS
        | IMAGE_EXTENSIONS
        | SLIDE_EXTENSIONS
        | DOC_EXTENSIONS
        | {".pdf"}
    )

    @classmethod
    def supports(cls, filename: str) -> bool:
        return Path(filename).suffix.lower() in cls.SUPPORTED_EXTENSIONS

    @classmethod
    def extract(
        cls,
        path: str | Path,
        filename: str,
        content_type: str | None = None,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> ExtractionResult:
        """Extract text from ``path``.

        ``on_progress(stage, current, total)`` is called as work proceeds:
        ``reading`` for plain extraction and ``ocr`` page by page for scans.
        """
        file_path = Path(path)
        suffix = Path(filename).suffix.lower()

        if on_progress is not None:
            on_progress("reading", 0, 0)

        if suffix in TEXT_EXTENSIONS:
            result = _read_plain(file_path)
        elif suffix == ".pdf":
            result = _read_pdf(file_path, on_progress=on_progress)
        elif suffix in DOC_EXTENSIONS:
            result = _read_docx(file_path)
        elif suffix == ".doc":
            raise ExtractionError(
                "Legacy .doc files are not supported - please save as .docx or PDF and re-upload."
            )
        elif suffix in SLIDE_EXTENSIONS:
            result = _read_pptx(file_path)
        elif suffix == ".ppt":
            raise ExtractionError(
                "Legacy .ppt files are not supported - please save as .pptx or PDF and re-upload."
            )
        elif suffix in HTML_EXTENSIONS:
            result = _read_html(file_path)
        elif suffix in IMAGE_EXTENSIONS:
            result = _read_image(file_path)
        elif content_type and content_type.startswith("text/"):
            result = _read_plain(file_path)
        else:
            raise ExtractionError(
                f"Unsupported file type '{suffix or content_type or 'unknown'}'. "
                f"Supported: {', '.join(cls.SUPPORTED_EXTENSIONS)}"
            )

        result.text = clean_text(result.text)
        if not result.text and not result.warnings:
            raise ExtractionError(
                "No readable text was found in this file. If it is a scan, try a text-based PDF."
            )
        return result


class ChunkProcessor:
    """Splits long text into overlapping, study-sized chunks."""

    DEFAULT_CHUNK_SIZE = 180  # words
    DEFAULT_OVERLAP = 30  # words

    @staticmethod
    def _split_long_paragraph(paragraph: str, chunk_size: int) -> list[str]:
        tokens = paragraph.split()
        if len(tokens) <= chunk_size * 2:
            return [paragraph]
        return [
            " ".join(tokens[i : i + chunk_size]) for i in range(0, len(tokens), chunk_size)
        ]

    @classmethod
    def chunk_text(
        cls,
        text: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> list[dict]:
        """Return chunks as dicts: ``{text, index, word_count, heading}``."""
        cleaned = clean_text(text)
        if not cleaned:
            return []

        chunk_size = max(20, int(chunk_size))
        overlap = max(0, min(int(overlap), chunk_size - 1))

        # 1. paragraph blocks, tracking the most recent short "heading" line.
        #    PDF extractors often return a whole page as one block with single
        #    newlines, so headings are detected inside a block too - but only when
        #    the line before them ends a sentence, which keeps wrapped prose lines
        #    from being mistaken for headings.
        blocks: list[tuple[str | None, str]] = []
        heading: str | None = None
        for raw_block in re.split(r"\n\s*\n", cleaned):
            lines = [line.strip() for line in raw_block.split("\n") if line.strip()]
            buffer: list[str] = []
            for line in lines:
                starts_section = bool(buffer) is False or bool(re.search(r"[.!?:;]$", buffer[-1]))
                if (
                    starts_section
                    and len(line.split()) <= 12
                    and cls._looks_like_heading(line)
                ):
                    if buffer:
                        blocks.append((heading, " ".join(buffer)))
                        buffer = []
                    heading = line.strip("# ").strip()
                    continue
                buffer.append(line)
            if buffer:
                blocks.append((heading, " ".join(buffer)))

        # 2. pack sentences up to chunk_size
        chunks: list[dict] = []
        current: list[str] = []
        current_heading: str | None = blocks[0][0] if blocks else None

        def flush(carry: bool = True) -> None:
            nonlocal current
            if not current:
                return
            body = " ".join(current).strip()
            if not body:
                current = []
                return
            total_words = len(body.split())
            chunks.append(
                {
                    "text": body,
                    "index": len(chunks),
                    "word_count": total_words,
                    "heading": current_heading,
                }
            )
            # Carry a small overlap so a fact split across a boundary stays retrievable.
            # Never let the overlap become the chunk, and never carry text across a
            # heading boundary - that would pollute the next topic's keywords.
            if not carry:
                current = []
                return
            max_overlap = min(overlap, total_words // 3)
            tail: list[str] = []
            tail_words = 0
            for sentence in reversed(current):
                n = len(sentence.split())
                if tail_words + n > max_overlap:
                    break
                tail.insert(0, sentence)
                tail_words += n
            current = tail

        for block_heading, block in blocks:
            if block_heading != current_heading:
                flush(carry=False)
                current_heading = block_heading
            for paragraph in cls._split_long_paragraph(block, chunk_size):
                sentences = split_sentences(paragraph) or [paragraph]
                for sentence in sentences:
                    sentence_words = len(sentence.split())
                    if sentence_words > chunk_size * 2:
                        for piece in cls._split_long_paragraph(sentence, chunk_size):
                            current.append(piece)
                            if sum(len(s.split()) for s in current) >= chunk_size:
                                flush()
                        continue
                    current.append(sentence)
                    if sum(len(s.split()) for s in current) >= chunk_size:
                        flush()
        if current:
            flush()

        # 3. fold a genuinely tiny trailing chunk into its predecessor, unless it
        #    belongs to its own section (a short heading is still a real topic).
        tiny_threshold = max(10, min(30, chunk_size // 8))
        if (
            len(chunks) >= 2
            and chunks[-1]["word_count"] < tiny_threshold
            and chunks[-1]["heading"] == chunks[-2]["heading"]
        ):
            tail = chunks.pop()
            chunks[-1]["text"] = f"{chunks[-1]['text']} {tail['text']}".strip()
            chunks[-1]["word_count"] = len(chunks[-1]["text"].split())

        for position, chunk in enumerate(chunks):
            chunk["index"] = position
        return chunks

    @staticmethod
    def _looks_like_heading(line: str) -> bool:
        text = line.strip()
        if not text or len(text) > 90:
            return False
        if text.startswith("#"):
            return True
        if text.endswith((".", "?", "!", ",", ";", ":")):
            return False
        # numbered / bulleted headings such as "2.1 Cell structure"
        if re.match(r"^\d+(\.\d+)*[).:]?\s+\S", text):
            return True
        # short Title Case lines ("Cell Structure", "Enzyme Kinetics")
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", text)
        if 0 < len(tokens) <= 8:
            capitalised = sum(1 for token in tokens if token[0].isupper())
            if capitalised / len(tokens) >= 0.7:
                return True
        return False
