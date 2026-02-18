from __future__ import annotations

import re

from pathlib import Path
from typing import List

from .errors import PdfReadError
from .types import PageText
from .blocks.lines import normalize_lines


def read_pdf_pages(pdf_path: str) -> List[PageText]:
    """
    Машиночитаемый PDF → список страниц с text + lines.
    OCR НЕ используется.
    """
    p = Path(pdf_path)
    if not p.exists() or not p.is_file():
        raise PdfReadError(f"PDF not found: {pdf_path}")

    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise PdfReadError(f"PyMuPDF (fitz) import failed: {e}") from e

    try:
        doc = fitz.open(str(p))
    except Exception as e:
        raise PdfReadError(f"Cannot open PDF: {pdf_path}: {e}") from e

    pages: List[PageText] = []
    try:
        all_text_parts: list[str] = []
        for i in range(doc.page_count):
            page = doc.load_page(i)
            txt = page.get_text("text") or ""
            all_text_parts.append(txt)
            lines = normalize_lines(txt.splitlines())
            pages.append(PageText(page_index=i, text=txt, lines=lines))
    finally:
        doc.close()
    
    # --- Guard: detect scanned/image-only PDF without extractable text layer ---
    # MOEK machine-readable PDFs always contain a meaningful header with many text lines.
    full_text = "\n".join(all_text_parts)
    non_empty_lines = [ln.strip() for ln in full_text.splitlines() if (ln or "").strip()]
    letters_count = len(re.findall(r"[A-Za-zА-Яа-я]", full_text))

    # Heuristic thresholds chosen to avoid false positives for normal statements.
    if len(non_empty_lines) < 5 or letters_count < 20:
        raise PdfReadError(
            "В PDF отсутствует текстовый слой (похоже на скан/изображение). "
            "Сервис работает только с машиночитаемыми PDF. Для этого файла нужен OCR."
        )

    return pages
