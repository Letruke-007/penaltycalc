# backend/app/api/pdfs.py
from __future__ import annotations

from typing import List, Optional

import fitz  # PyMuPDF
from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from ..extract.parsers.statement_inspect import inspect_statement

router = APIRouter(tags=["pdfs"])


class DebtorPreview(BaseModel):
    name: Optional[str] = None
    inn: Optional[str] = None


class InspectItemResult(BaseModel):
    filename: str
    debtor: DebtorPreview
    # NEW (non-breaking): OCR hint for scanned PDFs (no text layer)
    needs_ocr: bool = False
    inspect_warning: Optional[str] = None
    warnings: List[str] = []
    error: Optional[str] = None


class InspectResponse(BaseModel):
    items: List[InspectItemResult]


@router.post("/pdfs/inspect", response_model=InspectResponse)
async def inspect_pdfs(files: List[UploadFile] = File(...)) -> InspectResponse:
    items: List[InspectItemResult] = []

    for f in files:
        filename = f.filename or "file.pdf"
        try:
            data = await f.read()
            has_text_layer, lines = _probe_text_layer_and_extract_page1_lines(data)
            if not has_text_layer:
                # Scanned PDF (no text layer): don't fail batch; return a user-friendly warning.
                items.append(
                    InspectItemResult(
                        filename=filename,
                        debtor=DebtorPreview(name=None, inn=None),
                        needs_ocr=True,
                        inspect_warning=(
                            "В PDF отсутствует текстовый слой (похоже на скан). "
                            "Нужен OCR — файл не будет обработан."
                        ),
                        warnings=[],
                        error=None,
                    )
                )
                continue

            result = inspect_statement(lines, source_pdf=filename, filename=filename)

            items.append(
                InspectItemResult(
                    filename=result["filename"],
                    debtor=DebtorPreview(**result["debtor"]),
                    needs_ocr=False,
                    inspect_warning=None,
                    warnings=result.get("warnings") or [],
                    error=result.get("error"),
                )
            )
        except Exception as e:
            # Resilient: per-file failure shouldn't crash the whole batch
            items.append(
                InspectItemResult(
                    filename=filename,
                    debtor=DebtorPreview(name=None, inn=None),
                    needs_ocr=False,
                    inspect_warning=None,
                    warnings=[],
                    error=f"inspect endpoint error: {e!r}",
                )
            )

    return InspectResponse(items=items)


def _probe_text_layer_and_extract_page1_lines(pdf_bytes: bytes) -> tuple[bool, List[str]]:
    """
    Determine whether the PDF has a text layer and (if yes) extract page-1 lines.

    We deliberately keep it fast: check up to first 2 pages for any extractable text.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count == 0:
            return (False, [])

        # 1) Probe for text layer
        max_pages = min(2, doc.page_count)
        has_text = False
        for i in range(max_pages):
            page = doc.load_page(i)
            txt = (page.get_text("text") or "").strip()
            if txt:
                has_text = True
                break

        if not has_text:
            return (False, [])

        # 2) Extract page 1 lines for existing inspect parser
        page0 = doc.load_page(0)
        text0 = page0.get_text("text") or ""
    finally:
        doc.close()

    lines = [ln.strip() for ln in text0.splitlines()]
    return (True, [ln for ln in lines if ln])