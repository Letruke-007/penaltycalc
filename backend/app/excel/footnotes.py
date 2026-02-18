# backend/app/excel/footnotes.py
from __future__ import annotations

from typing import Optional

from .penalty_rules import (
    CAT_OTHER,
    CAT_TSJ,
    CAT_UK,
    CAT_OWNER_RES,
    CAT_OWNER_NONRES,
    normalize_category,
)

_P190_BASE = "ч. {part} ст. 15 Федерального закона от 27.07.2010 № 190-ФЗ «О теплоснабжении»"
_P416_BASE = "ч. {part} ст. 13 Федерального закона от 07.12.2011 № 416-ФЗ «О водоснабжении и водоотведении»"
_P329_SUFFIX = " с учетом ограничений величины ставки, предусмотренных постановлением Правительства РФ от 18.03.2025 № 329"


def _detect_resource_kind(contract_number: str) -> str:
    """Return one of: 'TE', 'GV', 'OTHER'."""
    s = (contract_number or "").upper()
    if "ТЭ" in s:
        return "TE"
    if "ГВС" in s or "ГВ" in s:
        return "GV"
    return "OTHER"


def rate_share_footnote(contract_number: str, category: Optional[str]) -> str:
    """Build the '* доля ставки определена ...' footnote string.

    Resource kind:
      - TE: 190-FZ only
      - GV/GVS: 416-FZ only
      - OTHER: both 190-FZ + 416-FZ

    Category affects article parts and whether 329-PP limitation suffix is appended.
    """
    cat_norm = normalize_category(category or "")
    if cat_norm not in {CAT_OTHER, CAT_TSJ, CAT_UK, CAT_OWNER_RES, CAT_OWNER_NONRES}:
        cat_norm = CAT_OTHER

    kind = _detect_resource_kind(contract_number)

    # --- TE: 190-FZ only ---
    if kind == "TE":
        part_map = {
            CAT_OTHER: ("9.1", False),
            CAT_TSJ: ("9.2", True),
            CAT_UK: ("9.2", True),
            CAT_OWNER_NONRES: ("9.4", False),
            CAT_OWNER_RES: ("9.4", True),
        }
        part, need_329 = part_map[cat_norm]
        text = _P190_BASE.format(part=part)
        if need_329:
            text += _P329_SUFFIX
        return f"* доля ставки определена в соответствии с {text}."

    # --- GV/GVS: 416-FZ only ---
    if kind == "GV":
        part_map = {
            CAT_OTHER: ("6.2", False),
            CAT_TSJ: ("6.3", True),
            CAT_UK: ("6.4", True),
            CAT_OWNER_NONRES: ("6.5", False),
            CAT_OWNER_RES: ("6.5", True),
        }
        part, need_329 = part_map[cat_norm]
        text = _P416_BASE.format(part=part)
        if need_329:
            text += _P329_SUFFIX
        return f"* доля ставки определена в соответствии с {text}."

    # --- OTHER: combined ---
    map_190 = {
        CAT_OTHER: "9.1",
        CAT_TSJ: "9.2",
        CAT_UK: "9.3",
        CAT_OWNER_NONRES: "9.4",
        CAT_OWNER_RES: "9.4",
    }
    map_416 = {
        CAT_OTHER: "6.2",
        CAT_TSJ: "6.3",
        CAT_UK: "6.4",
        CAT_OWNER_NONRES: "6.5",
        CAT_OWNER_RES: "6.5",
    }
    need_329 = cat_norm in {CAT_TSJ, CAT_UK, CAT_OWNER_RES}

    text = f"{_P190_BASE.format(part=map_190[cat_norm])}, {_P416_BASE.format(part=map_416[cat_norm])}"
    if need_329:
        text += _P329_SUFFIX
    return f"* доля ставки определена в соответствии с {text}."
