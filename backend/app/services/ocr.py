"""Optional OCR support for scanned PDFs and image uploads.

Two engines are supported and picked in this order:

1. ``tesseract`` through ``pytesseract`` - fast, but needs the system binary.
2. ``rapidocr-onnxruntime`` - pure pip install, ships its own models.

PDF pages are rasterised with ``pypdfium2``, falling back to poppler's
``pdftoppm`` when pdfium is unavailable. Every dependency here is optional: when
nothing is installed the caller gets a clear warning instead of a crash.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Iterator

#: Engine used for the last successful load (``None`` until something is tried).
_ENGINE_NAME: str | None = None
_ENGINE: object | None = None
_LOADED = False
_LOCK = threading.Lock()


def _load_engine() -> tuple[str | None, object | None]:
    """Import an OCR engine once per process (both options are expensive)."""
    global _ENGINE_NAME, _ENGINE, _LOADED
    with _LOCK:
        if _LOADED:
            return _ENGINE_NAME, _ENGINE
        _LOADED = True

        try:  # pragma: no cover - depends on the host
            import pytesseract  # type: ignore

            pytesseract.get_tesseract_version()
            _ENGINE_NAME, _ENGINE = "tesseract", pytesseract
            return _ENGINE_NAME, _ENGINE
        except Exception:  # noqa: BLE001 - optional dependency
            pass

        try:  # pragma: no cover - depends on the host
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            _ENGINE_NAME, _ENGINE = "rapidocr", RapidOCR()
            return _ENGINE_NAME, _ENGINE
        except Exception:  # noqa: BLE001 - optional dependency
            pass

        _ENGINE_NAME, _ENGINE = None, None
        return _ENGINE_NAME, _ENGINE


def engine_name() -> str | None:
    """Return the OCR engine that will be used, or ``None`` when unavailable."""
    return _load_engine()[0]


def can_rasterize() -> bool:
    """True when PDF pages can be turned into images."""
    try:
        import pypdfium2  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return shutil.which("pdftoppm") is not None


def available() -> bool:
    return engine_name() is not None and can_rasterize()


def ocr_image(image) -> str:
    """OCR a PIL image. Returns ``""`` when no engine is installed."""
    name, engine = _load_engine()
    if name == "tesseract":
        try:
            return (engine.image_to_string(image) or "").strip()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - a broken page should not kill the upload
            return ""
    if name == "rapidocr":
        try:
            result, _ = engine(image)  # type: ignore[operator]
        except Exception:  # noqa: BLE001
            return ""
        lines = [line[1] for line in (result or []) if len(line) > 1 and line[1]]
        return "\n".join(lines).strip()
    return ""


def _render_with_pdfium(path: Path, max_pages: int, dpi: int) -> Iterator[object]:
    import pypdfium2 as pdfium  # type: ignore

    document = pdfium.PdfDocument(str(path))
    try:
        total = min(len(document), max_pages)
        for index in range(total):
            page = document[index]
            yield page.render(scale=dpi / 72).to_pil()
    finally:
        document.close()


def _render_with_poppler(path: Path, max_pages: int, dpi: int) -> Iterator[object]:
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                "pdftoppm",
                "-r",
                str(dpi),
                "-png",
                "-l",
                str(max_pages),
                str(path),
                str(Path(tmp) / "page"),
            ],
            capture_output=True,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            return
        for png in sorted(Path(tmp).glob("page*.png")):
            with Image.open(png) as image:
                yield image.convert("RGB").copy()


def pdf_page_images(path: str | Path, max_pages: int = 25, dpi: int = 150) -> Iterator[object]:
    """Yield up to ``max_pages`` rendered pages as PIL images."""
    file_path = Path(path)
    try:
        yield from _render_with_pdfium(file_path, max_pages, dpi)
        return
    except Exception:  # noqa: BLE001 - fall back to poppler
        pass
    if shutil.which("pdftoppm"):
        try:
            yield from _render_with_poppler(file_path, max_pages, dpi)
        except Exception:  # noqa: BLE001
            return


def ocr_pdf(
    path: str | Path,
    *,
    max_pages: int = 25,
    dpi: int = 150,
) -> tuple[str, list[str], int]:
    """OCR a PDF.

    Returns ``(text, warnings, pages_read)``. Blank pages are skipped silently;
    the caller decides what to do when nothing could be read.
    """
    engine = engine_name()
    if engine is None:
        return "", [
            "This PDF has no selectable text (it looks scanned) and no OCR engine "
            "is installed. Install one with: pip install rapidocr-onnxruntime"
        ], 0
    if not can_rasterize():
        return "", [
            "This PDF has no selectable text (it looks scanned) and no PDF rasteriser "
            "is installed. Install one with: pip install pypdfium2"
        ], 0

    pages: list[str] = []
    pages_read = 0
    for image in pdf_page_images(path, max_pages=max_pages, dpi=dpi):
        pages_read += 1
        text = ocr_image(image)
        if text:
            pages.append(text)

    if not pages:
        return "", [f"OCR ({engine}) found no readable text in this PDF."], pages_read

    warnings = [
        f"Recovered text from a scanned PDF with OCR ({engine}, {pages_read} "
        f"page{'s' if pages_read != 1 else ''})."
    ]
    return "\n\n".join(pages), warnings, pages_read
