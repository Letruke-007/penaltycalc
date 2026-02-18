from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Ищем первое "денежное" число в строке.
# Поддержка:
#  - разделители тысяч пробелами/NBSP
#  - десятичный разделитель "," или "."
#  - отрицательные значения "-" или "−"
_MONEY_TOKEN_RE = re.compile(
    r"(?P<sign>-|−)?(?P<int>\d{1,3}(?:[ \u00A0]\d{3})*|\d+)(?P<dec>[.,]\d{2})"
)


def money_to_str(raw: str) -> str:
    """
    Normalize money to JSON string "12345.67".

    Accepts:
      - "306 529.69"
      - "1 854 076,00"
      - "-153 824,51"
      - lines containing multiple numbers -> takes the first money-like token.
    """
    if raw is None:
        raise ValueError("money is None")

    s = str(raw).strip()
    m = _MONEY_TOKEN_RE.search(s)
    if not m:
        raise ValueError(f"money token not found: {raw!r}")

    sign = m.group("sign") or ""
    sign = "-" if sign in ("-", "−") else ""

    int_part = m.group("int").replace(" ", "").replace("\u00A0", "")
    dec_part = m.group("dec").replace(",", ".")

    try:
        val = Decimal(f"{sign}{int_part}{dec_part}")
    except InvalidOperation as e:
        raise ValueError(f"invalid money token: {raw!r}") from e

    return f"{val:.2f}"
