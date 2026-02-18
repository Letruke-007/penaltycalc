from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple

_DATE_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")


def ensure_ddmmyyyy(s: str) -> str:
    s = (s or "").strip()
    m = _DATE_RE.match(s)
    if not m:
        raise ValueError(f"Invalid date (DD.MM.YYYY) token: {s!r}")
    # доп. валидация на корректность даты
    dd, mm, yyyy = map(int, m.groups())
    datetime(yyyy, mm, dd)  # может бросить ValueError
    return s


def last_day_of_month(mm_yyyy: str) -> str:
    """
    mm_yyyy: "03.2025" → "31.03.2025"
    """
    mm_yyyy = (mm_yyyy or "").strip()
    m = re.match(r"^(\d{2})\.(\d{4})$", mm_yyyy)
    if not m:
        raise ValueError(f"Invalid period token (MM.YYYY): {mm_yyyy!r}")
    mm = int(m.group(1))
    yyyy = int(m.group(2))
    last = calendar.monthrange(yyyy, mm)[1]
    return f"{last:02d}.{mm:02d}.{yyyy:04d}"
