from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from ...normalize.dates import ensure_ddmmyyyy
from ..errors import ParseError


def _find_generated_at_and_calc_date(lines: list[str]):
    # NEW: deterministic guard for image-only/scanned PDFs (no text layer)
    non_empty = [ln.strip() for ln in lines if (ln or "").strip()]
    if len(non_empty) < 5:
        # 5 — константа-guard: шапка всегда даёт больше строк на машиночитаемых PDF
        raise ParseError("no extractable text layer in PDF (likely scanned image); OCR is required")

    generated_at: str | None = None
    calc_date: str | None = None

    # "Дата : 08.02.2024" / "Дата: 08.02.2024" (+варианты пробелов), но НЕ "Дата с: ..."
    _DOC_DATE_RE = re.compile(r"^Дата(?!\s*с)\s*:\s*(\d{2}\.\d{2}\.\d{4})$")

    for raw in non_empty:
        ln = raw.strip()

        # generated_at: "11.12.2025 11:47"
        m = _GEN_DT_RE.match(ln)
        if m and generated_at is None:
            generated_at = f"{m.group(1)} {m.group(2)}"
            continue

        # calc_date (document date): "Дата : 08.02.2024" / "Дата: 08.02.2024"
        m = _DOC_DATE_RE.match(ln)
        if m and calc_date is None:
            calc_date = m.group(1)
            continue

        if generated_at is not None and calc_date is not None:
            break

    if generated_at is None:
        raise ParseError("generated_at not found")
    if calc_date is None:
        raise ParseError("calc_date not found (no document date)")

    return generated_at, calc_date


# "11.12.2025 11:47"
_GEN_DT_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})$")

# просто "11.12.2025"
_DATE_ONLY_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})$")

# "Дата с: 01.08.2025" (+варианты пробелов)
_FROM_RE = re.compile(r"^Дата\s+с\s*:\s*(\d{2}\.\d{2}\.\d{4})$")


def parse_meta(lines: List[str], source_pdf: str) -> Tuple[Dict, str, str]:
    """
    Returns:
      meta: {source_pdf, generated_at}
      period_from: "DD.MM.YYYY"
      calc_date: "DD.MM.YYYY"  (дата формирования справки)
    """
    generated_at, calc_date = _find_generated_at_and_calc_date(lines)
    period_from = _find_period_from(lines)

    return {
        "source_pdf": source_pdf,
        "generated_at": generated_at,
    }, period_from, calc_date


def _find_generated_at_and_calc_date(lines: List[str]) -> Tuple[str, str]:
    # 1) Ищем "DD.MM.YYYY HH:MM" вверху (как было)
    for ln in lines[:60]:
        m = _GEN_DT_RE.match(ln)
        if m:
            d = ensure_ddmmyyyy(m.group(1))
            t = m.group(2)
            dt = datetime.strptime(f"{d} {t}", "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), d

    # 2) Ищем просто дату "DD.MM.YYYY" вверху (как было)
    for ln in lines[:60]:
        m = _DATE_ONLY_RE.match(ln)
        if m:
            d = ensure_ddmmyyyy(m.group(1))
            dt = datetime.strptime(d, "%d.%m.%Y").replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), d

    # 3) FALLBACK: дата формирования может быть в футере/ниже по тексту.
    # Берём наиболее часто встречающуюся дату/датавремя по всему документу,
    # исключая 'Дата с: ...' (это period_from, не calc_date).
    dt_counts: Dict[str, int] = {}     # key: "DD.MM.YYYY HH:MM"
    d_counts: Dict[str, int] = {}      # key: "DD.MM.YYYY"

    for raw in lines:
        ln = (raw or "").strip()
        if not ln:
            continue

        # исключаем period_from
        if _FROM_RE.match(ln):
            continue

        mdt = _GEN_DT_RE.match(ln)
        if mdt:
            d = ensure_ddmmyyyy(mdt.group(1))
            t = mdt.group(2)
            key = f"{d} {t}"
            dt_counts[key] = dt_counts.get(key, 0) + 1
            continue

        md = _DATE_ONLY_RE.match(ln)
        if md:
            d = ensure_ddmmyyyy(md.group(1))
            d_counts[d] = d_counts.get(d, 0) + 1
            continue

    # Prefer datetime-with-time if it clearly repeats (typical footer).
    if dt_counts:
        best_dt, _ = max(dt_counts.items(), key=lambda kv: kv[1])
        d_part, t_part = best_dt.split(" ", 1)
        dt = datetime.strptime(f"{d_part} {t_part}", "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), d_part

    if d_counts:
        best_d, _ = max(d_counts.items(), key=lambda kv: kv[1])
        dt = datetime.strptime(best_d, "%d.%m.%Y").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ"), best_d

    raise ParseError("calc_date not found (no document date)")


def _find_period_from(lines: List[str]) -> str:
    for ln in lines[:120]:
        m = _FROM_RE.match(ln)
        if m:
            return ensure_ddmmyyyy(m.group(1))
    raise ParseError("period.from not found (expected 'Дата с: DD.MM.YYYY')")
