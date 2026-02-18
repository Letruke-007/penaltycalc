# backend/app/extract/parsers/statement_inspect.py
from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..errors import ParseError
from .statement_header import parse_header
from .statement_parser import _extract_consumer_name_from_header, _parse_bottom_block


_BAD_NAME_PATTERNS: List[re.Pattern] = [
    # common table header right after "Потребитель ...:"
    re.compile(r"^\s*Месяц,\s*год\s*$", re.IGNORECASE),
    re.compile(r"^\s*Месяц,\s*год\b", re.IGNORECASE),
    re.compile(r"^\s*Сумма\b", re.IGNORECASE),
    re.compile(r"^\s*Дата\b", re.IGNORECASE),
    # column header lines like: "Месяц, год Сумма Дата Сумма"
    re.compile(r"^\s*Месяц,\s*год\s+Сумма\s+Дата\s+Сумма\s*$", re.IGNORECASE),
    # "1 2 3 4 7" etc.
    re.compile(r"^\s*\d+(\s+\d+){2,}\s*$"),
]


def inspect_statement(lines: List[str], *, source_pdf: str, filename: str) -> Dict:
    """
    Fast inspect: extract only debtor.name + debtor.inn from text layer.
    Must be resilient for batch usage: does not raise.
    """
    warnings: List[str] = []
    debtor_name: Optional[str] = None
    debtor_inn: Optional[str] = None

    # INN via parse_header()
    try:
        debtor, _contract = parse_header(lines)
        inn = (debtor.get("inn") or "").strip()
        if inn:
            debtor_inn = inn
        else:
            warnings.append("debtor.inn empty after parse_header")
    except ParseError as e:
        warnings.append(str(e))
    except Exception as e:
        warnings.append(f"inspect.inn unexpected error: {e!r}")

    # Name: prefer "Потребитель ...:" block, BUT validate candidate.
    # Fallback to bottom-block OPF scan (reliable for many PDFs where name is placed later).
    try:
        nm = _extract_consumer_name_from_header(lines, start_from=0)
        nm = _clean_name(nm)

        # Guard: avoid false positives like "Месяц, год" (table headers)
        if nm and _looks_like_table_header(nm):
            warnings.append(f"debtor.name candidate rejected (looks like table header): {nm!r}")
            nm = None

        if not nm:
            _contract_no, nm2 = _parse_bottom_block(lines)  # may raise ParseError
            nm = _clean_name(nm2)

        if nm:
            debtor_name = nm
        else:
            warnings.append("debtor.name not found")
    except ParseError as e:
        warnings.append(str(e))
    except Exception as e:
        warnings.append(f"inspect.name unexpected error: {e!r}")

    error: Optional[str] = None
    if not debtor_inn and not debtor_name:
        error = "inspect failed: debtor.inn and debtor.name are missing"

    return {
        "filename": filename,
        "source_pdf": source_pdf,
        "debtor": {"name": debtor_name, "inn": debtor_inn},
        "warnings": warnings,
        "error": error,
    }


def _looks_like_table_header(name: str) -> bool:
    s = " ".join(name.strip().split())
    if not s:
        return True

    for pat in _BAD_NAME_PATTERNS:
        if pat.match(s):
            return True

    # additional heuristic: too short and contains typical table words
    low = s.lower()
    if len(s) <= 20 and ("месяц" in low or "год" in low or "сумма" in low or "дата" in low):
        return True

    return False


def _clean_name(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s2 = " ".join(str(s).strip().split())
    return s2 or None
