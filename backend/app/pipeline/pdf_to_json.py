from __future__ import annotations

from typing import Dict, Optional

from ..extract.pdf_reader import read_pdf_pages
from ..extract.parsers.statement_parser import parse_statement


def pdf_to_json(
    pdf_path: str,
    *,
    calc_date: str,
    category: Optional[str],
    rate_percent: float,
    overdue_start_day: int,
) -> Dict:
    pages = read_pdf_pages(pdf_path)

    all_lines: list[str] = []
    for p in pages:
        all_lines.extend(p.lines)

    return parse_statement(
        all_lines,
        source_pdf=pdf_path,
        category=category,
        calc_date_override=calc_date,
        rate_percent=rate_percent,
        overdue_start_day=overdue_start_day,
    )
