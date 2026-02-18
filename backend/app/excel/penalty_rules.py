# backend/app/excel/penalty_rules.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Tuple


# Канонические названия (внутренние)
CAT_OTHER = "Прочие"
CAT_TSJ = "ТСЖ, ЖСК, ЖК"
CAT_UK = "Управляющая организация"
CAT_OWNER_RES = "Собственники жилых помещений в МКД"
CAT_OWNER_NONRES = "Собственники нежилых помещений в МКД"


# Алиасы входных значений из UI/JSON
# (UI сейчас отдаёт "УК" — именно это и нужно сматчить)
_CATEGORY_ALIASES = {
    # Прочие
    "прочие": CAT_OTHER,

    # ТСЖ
    "тсж, жск, жк": CAT_TSJ,
    "тсж": CAT_TSJ,
    "жск": CAT_TSJ,
    "жк": CAT_TSJ,
    "жилищный кооператив": CAT_TSJ,

    # УК
    "ук": CAT_UK,
    "управляющая организация": CAT_UK,
    "управляющие организации": CAT_UK,

    # Собственники
    "собственники жилых помещений в мкд": CAT_OWNER_RES,
    "собственник жилого помещения в мкд": CAT_OWNER_RES,
    "собственники нежилых помещений в мкд": CAT_OWNER_NONRES,
    "собственник нежилого помещения в мкд": CAT_OWNER_NONRES,
}


def normalize_category(category: str) -> str:
    c = (category or "").strip()
    if not c:
        return CAT_OTHER
    return _CATEGORY_ALIASES.get(c.lower(), c)


@dataclass(frozen=True)
class FractionSchedule:
    # (start_day, end_day_inclusive_or_None, fraction)
    segments: Tuple[Tuple[int, int | None, Decimal], ...]

    def fraction_for_day(self, day_no: int) -> Decimal:
        for start, end, frac in self.segments:
            if day_no >= start and (end is None or day_no <= end):
                return frac
        return Decimal("0")

    def boundary_days(self) -> List[int]:
        # дни, когда начинается новый сегмент (кроме 1)
        return sorted({start for start, _, _ in self.segments if start != 1})


# ----------------------------
# Schedules (по вашему ТЗ)
# ----------------------------

# Прочие: всегда 1/130
SCHED_OTHER = FractionSchedule(
    segments=((1, None, Decimal(1) / Decimal(130)),)
)

# ТСЖ/ЖСК/ЖК: 1..30 = 0; 31..90 = 1/300; 91+ = 1/130
SCHED_TSJ = FractionSchedule(
    segments=(
        (1, 30, Decimal("0")),
        (31, 90, Decimal(1) / Decimal(300)),
        (91, None, Decimal(1) / Decimal(130)),
    )
)

# УК: 1..60 = 1/300; 61..90 = 1/170; 91+ = 1/130
SCHED_UK = FractionSchedule(
    segments=(
        (1, 60, Decimal(1) / Decimal(300)),
        (61, 90, Decimal(1) / Decimal(170)),
        (91, None, Decimal(1) / Decimal(130)),
    )
)

# Собственники:
# - жилые: 1..30 = 0; 31..90 = 1/300; 91+ = 1/130
# - нежилые: всегда 1/130
SCHED_OWNER_RES = SCHED_TSJ
SCHED_OWNER_NONRES = SCHED_OTHER


def schedule_for_category(category: str) -> FractionSchedule:
    cat = normalize_category(category)
    if cat == CAT_TSJ:
        return SCHED_TSJ
    if cat == CAT_UK:
        return SCHED_UK
    if cat == CAT_OWNER_RES:
        return SCHED_OWNER_RES
    if cat == CAT_OWNER_NONRES:
        return SCHED_OWNER_NONRES
    return SCHED_OTHER


def fraction_for_day(category: str, day_no: int) -> Decimal:
    return schedule_for_category(category).fraction_for_day(day_no)


def split_by_fraction_boundaries(
    *,
    category: str,
    start: date,
    end: date,
    base_overdue_start: date,
) -> List[Tuple[date, date, Decimal]]:
    """
    Делит [start..end] на подпериоды с постоянной долей K.
    base_overdue_start соответствует day_no=1.
    Возвращает список (sub_start, sub_end, fraction).
    """
    cat = normalize_category(category)
    sched = schedule_for_category(cat)

    # даты границ сегментов (в абсолютных датах)
    boundary_dates: List[date] = []
    for boundary_day in sched.boundary_days():
        bd = base_overdue_start + timedelta(days=boundary_day - 1)
        boundary_dates.append(bd)

    boundary_dates = sorted(d for d in boundary_dates if start <= d <= end)

    segments: List[Tuple[date, date, Decimal]] = []
    cur = start

    for bd in boundary_dates:
        if bd > cur:
            seg_end = bd - timedelta(days=1)
            day_no = (cur - base_overdue_start).days + 1
            segments.append((cur, seg_end, fraction_for_day(cat, day_no)))
            cur = bd

    if cur <= end:
        day_no = (cur - base_overdue_start).days + 1
        segments.append((cur, end, fraction_for_day(cat, day_no)))

    return segments
