from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from app.pipeline.pdf_to_json import pdf_to_json
from app.contracts.statement import StatementRoot

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
PDF_DIR = FIXTURES / "pdf"
EXPECTED_DIR = FIXTURES / "expected_json"


# Явное сопоставление: какой PDF должен дать какой expected JSON
CASES = [
    (
        "07.620535-ТЭ  03.2025-04.2025.pdf",
        "etalon_07.620535-ТЭ_03.2025-04.2025.json",
    ),
    (
        "44039 справка (1).pdf",
        "etalon_44039_03.2024-07.2024.json",
    ),
]


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _strip_noise(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Убираем поля, которые могут отличаться от прогона к прогону:
      - meta.generated_at (время генерации)
      - meta.source_pdf (локальный путь)
    Остальное сравниваем строго.
    """
    doc = json.loads(json.dumps(doc, ensure_ascii=False))  # deep-copy

    meta = doc.get("meta") or {}
    if isinstance(meta, dict):
        meta.pop("generated_at", None)
        meta.pop("source_pdf", None)

    return doc


@pytest.mark.parametrize("pdf_name, expected_name", CASES)
def test_pdf_to_json_matches_expected(pdf_name: str, expected_name: str) -> None:
    pdf_path = PDF_DIR / pdf_name
    expected_path = EXPECTED_DIR / expected_name

    if not pdf_path.exists():
        pytest.skip(f"Missing PDF fixture: {pdf_path}")

    expected_raw = _load_json(expected_path)
    expected = StatementRoot.model_validate(expected_raw)  # контракт + forbid-extra

    actual_raw = pdf_to_json(str(pdf_path), category=None)  # category теперь опциональная
    actual = StatementRoot.model_validate(actual_raw)

    expected_cmp = _strip_noise(expected.model_dump(by_alias=True))
    actual_cmp = _strip_noise(actual.model_dump(by_alias=True))

    assert actual_cmp == expected_cmp, (
        "PDF → JSON mismatch with golden fixture.\n"
        f"PDF: {pdf_name}\nExpected: {expected_name}"
    )
