from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ...normalize.dates import ensure_ddmmyyyy
from ..errors import ParseError

_INN_RE = re.compile(r"\bИНН\s+(\d{10,12})\b")
# В шапке рядом с ИНН часто есть "Дата : 27.09.2023"
_CONTRACT_DATE_RE = re.compile(r"^Дата\s*:\s*(\d{2}\.\d{2}\.\d{4})$")


def parse_header(lines: List[str]) -> Tuple[Dict, Dict]:
    debtor = {"name": "", "inn": _find_inn(lines)}
    contract = {"number": "", "date": _find_contract_date(lines)}
    return debtor, contract


def _find_inn(lines: List[str]) -> str:
    for ln in lines[:120]:
        m = _INN_RE.search(ln)
        if m:
            return m.group(1)
    raise ParseError("debtor.inn not found (expected 'ИНН ##########')")


def _find_contract_date(lines: List[str]) -> str:
    # ищем "Дата : DD.MM.YYYY" в первых 120 строках
    for ln in lines[:160]:
        m = _CONTRACT_DATE_RE.match(ln)
        if m:
            return ensure_ddmmyyyy(m.group(1))
    # не всегда обязана присутствовать — но по твоим образцам есть
    raise ParseError("contract.date not found (expected 'Дата : DD.MM.YYYY')")
