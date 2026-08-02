"""Rasterize PDF pages and OCR them with Tesseract.

Used as a fallback when pdfplumber's embedded text layer is empty or
garbled (common for scanned OGE 278-T filings). Requires system packages:

* Tesseract OCR (``tesseract`` on PATH)
* Poppler (``pdftoppm`` / pdf2image dependency)

Call :func:`ocr_available` before relying on OCR in ingest so empty parses
stay retryable when the toolchain is missing.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


class OcrUnavailableError(RuntimeError):
    """Raised when Tesseract and/or Poppler are not installed or not callable."""


@lru_cache(maxsize=1)
def ocr_available() -> bool:
    """Return True when pdf2image + pytesseract + system binaries work."""
    try:
        import pytesseract
        from pdf2image.exceptions import PDFInfoNotInstalledError

        # Tesseract binary
        pytesseract.get_tesseract_version()
    except Exception:
        return False

    try:
        from pdf2image import convert_from_path

        # Probe poppler without needing a real PDF: missing binary raises
        # PDFInfoNotInstalledError (or OSError) when convert is attempted.
        # We only check import + that the helper is present; a full convert
        # probe needs a file. Treat import success as "likely available" and
        # let ocr_page_text raise OcrUnavailableError on first real failure.
        _ = convert_from_path
        _ = PDFInfoNotInstalledError
    except Exception:
        return False
    return True


def ocr_page_text(
    pdf_path: Path,
    page_index: int,
    *,
    dpi: int = 300,
    psm: int = 6,
) -> str:
    """OCR a single 0-based page and return plain text.

    Defaults favor scanned OGE 278-T tables: 300 DPI + Tesseract PSM 6
    (assume a uniform block of text).

    Raises
    ------
    OcrUnavailableError
        When Tesseract or Poppler is missing / not callable.
    ValueError
        When ``page_index`` is out of range for the PDF.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if page_index < 0:
        raise ValueError(f"page_index must be >= 0, got {page_index}")

    try:
        import pytesseract
        from pdf2image import convert_from_path
        from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
    except ImportError as exc:
        raise OcrUnavailableError(
            "OCR dependencies missing (pip install pdf2image pytesseract Pillow). "
            "Also install system packages: tesseract-ocr and poppler-utils."
        ) from exc

    try:
        # pdf2image uses 1-based first_page/last_page.
        images = convert_from_path(
            str(pdf_path),
            dpi=dpi,
            first_page=page_index + 1,
            last_page=page_index + 1,
        )
    except PDFInfoNotInstalledError as exc:
        raise OcrUnavailableError(
            "Poppler is not installed or not on PATH (pdf2image needs pdftoppm). "
            "On Debian/Ubuntu: apt install poppler-utils. "
            "On Windows: install Poppler and add its bin/ to PATH."
        ) from exc
    except PDFPageCountError as exc:
        raise ValueError(f"Could not read page count for {pdf_path}: {exc}") from exc
    except Exception as exc:
        message = str(exc).lower()
        if "tesseract" in message or "poppler" in message or "pdftoppm" in message:
            raise OcrUnavailableError(str(exc)) from exc
        raise

    if not images:
        raise ValueError(f"No image rendered for page {page_index} of {pdf_path}")

    image = images[0]
    try:
        from PIL import ImageEnhance, ImageOps

        # Light preprocessing helps dense municipal-bond tables on scans.
        gray = ImageOps.grayscale(image)
        image = ImageEnhance.Contrast(gray).enhance(1.4)
    except Exception:
        pass

    try:
        config = f"--psm {int(psm)}"
        return pytesseract.image_to_string(image, config=config) or ""
    except pytesseract.TesseractNotFoundError as exc:
        raise OcrUnavailableError(
            "Tesseract is not installed or not on PATH. "
            "On Debian/Ubuntu: apt install tesseract-ocr. "
            "On Windows: install Tesseract-OCR and add it to PATH."
        ) from exc
