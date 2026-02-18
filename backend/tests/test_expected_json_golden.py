from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest

from app.contracts.statement import StatementRoot

MONEY_RE = re.compile(r"^-?\d+\.\d{2}$")


def _d(m: str) -> Decimal:
    if not isinstance(m, str) or not MONEY_RE.match(m):
        raise AssertionError(f"Invalid money format: {m!r} (expected '12345.67')")
    try:
        return Decimal(m)
    except InvalidOperation as e:
        raise AssertionError(f"Invalid Decimal for money {m!r}: {e}") from e


def _sum_amounts(items) -> Decimal:
    total = Decimal("0.00")
    for it in items:
        total += _d(it.amount)
    return total


@pytest.mark.parametrize(
    "path",
    sorted(
        Path(__file__).resolve().parent.joinpath("fixtures", "expected_json").glob("*.json")
    ),
)
def test_expected_json_is_valid_and_consistent(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))

    # 1) Валидируем структуру и forbid-extra через Pydantic
    doc = StatementRoot.model_validate(raw)

    st = doc.statement

    # 2) Проверяем формат денег (строго "12345.67") и арифметику totals
    charged_sum = _sum_amounts(st.charges)
    paid_sum = _sum_amounts(st.payments)

    totals_charged = _d(st.totals.charged)
    totals_paid = _d(st.totals.paid)
    totals_debt = _d(st.totals.debt)

    assert charged_sum == totals_charged, f"{path.name}: sum(charges) mismatch"
    assert paid_sum == totals_paid, f"{path.name}: sum(payments) mismatch"
    assert totals_charged - totals_paid == totals_debt, f"{path.name}: debt mismatch"

    # 3) Category необязательное: если есть — строка, если нет — ок.
    if st.category is not None:
        assert isinstance(st.category, str) and st.category.strip(), f"{path.name}: bad category"
