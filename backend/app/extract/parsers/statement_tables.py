from __future__ import annotations

from app.core.errors import UserFacingError
import calendar
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple


_MONEY_TOKEN_RE = re.compile(
    r"(?P<sign>-)?(?P<int>\d{1,3}(?:[ \u00A0\u202F]\d{3})+|\d+)(?:[.,](?P<frac>\d{1,2}))?"
)

# Guard: full date in line (footer like "2 14.01.2026") must not be treated as money.
_FULL_DATE_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{4}\b")

# Guard: time in line (header like "13.01.2026 14:41") must not be treated as money.
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")

# Domain rule: amounts always contain cents (two decimals) in source text: ",dd" or ".dd"
_CENTS_RE = re.compile(r"[,.]\d{2}\b")


def money_to_str(s: str) -> str:
    """
    Convert 'human' money from PDF text layer to canonical '12345.67' (string).
    Accepts:
      - '909 962.70'
      - '909 962,70'
      - '-14 693.73'
      - '0.00'
      - '-0.03'
    Ignores surrounding text: extracts first money-like token.
    """
    if s is None:
        raise ValueError("money_to_str: empty")

    txt = str(s).strip()
    m = _MONEY_TOKEN_RE.search(txt)
    if not m:
        raise ValueError(f"money_to_str: not a money token: {txt!r}")

    sign = "-" if m.group("sign") else ""
    int_part = (
        (m.group("int") or "")
        .replace(" ", "")
        .replace("\u00a0", "")
        .replace("\u202f", "")
    )
    frac = m.group("frac")
    if frac is None:
        frac = "00"
    elif len(frac) == 1:
        frac = frac + "0"

    # normalize leading zeros
    if int_part == "":
        int_part = "0"

    return f"{sign}{int_part}.{frac}"


# ---------------------------
# Helpers / tolerances
# ---------------------------

TOL = Decimal("0.01")


def _d(s: str) -> Decimal:
    # money_to_str() returns normalized "12345.67"
    return Decimal(s).quantize(TOL, rounding=ROUND_HALF_UP)


def _close(a: Decimal, b: Decimal, tol: Decimal = TOL) -> bool:
    return (a - b).copy_abs() <= tol


def _try_money_line(ln: str) -> Optional[str]:
    """
    Try parse a money amount from a line, returning normalized money string (e.g. "12345.67"),
    or None if the line should not be treated as containing a valid amount.

    Domain rule (MOEK): начисления/оплаты всегда с копейками (ровно 2 знака), целых сумм быть не может.
    """
    ln = (ln or "").strip()
    if not ln:
        return None

    # Guards against footer/header artifacts
    if _FULL_DATE_RE.search(ln):  # e.g. "14.01.2026"
        return None
    if _TIME_RE.search(ln):  # e.g. "14:41"
        return None

    # money must have cents in the source text: ",dd" or ".dd"
    # This prevents year/page-number artifacts like "2026" -> "202.00".
    if not _CENTS_RE.search(ln):
        return None

    try:
        s = money_to_str(ln)
    except Exception:
        return None

    # Keep existing small-int/page-number guard (mostly redundant now, but harmless)
    try:
        d = Decimal(s)
    except Exception:
        return None

    # Reject *pure* small integers like page numbers (1..8) ONLY when they appear without cents.
    # Note: real amounts like "3,00" / "3.00" must be kept.
    if re.fullmatch(r"\d{1,2}", ln) and Decimal("0") < abs(d) < Decimal("9"):
        return None

    return s


def _try_money_values(ln: str) -> List[str]:
    """
    Extract ALL money tokens from a line (normalized "12345.67" strings).

    Needed for lines like:
      - month totals: "301 863.83 287 348.03"
      - doc totals:   "7 542 348.95 6 840 566.46 701 782.49"

    Applies same guards as _try_money_line:
      - ignore full dates / time
      - require cents
      - ignore small integer page numbers
    """
    ln = (ln or "").strip()
    if not ln:
        return []
    if _FULL_DATE_RE.search(ln):
        return []
    if _TIME_RE.search(ln):
        return []

    out: List[str] = []
    for m in _MONEY_TOKEN_RE.finditer(ln):
        token = m.group(0)
        if not _CENTS_RE.search(token):
            continue
        try:
            s = money_to_str(token)
            d = Decimal(s)
        except Exception:
            continue
        if (
            re.fullmatch(r"\d{1,2}", token)
            and d == d.to_integral()
            and Decimal("0") < abs(d) < Decimal("9")
        ):
            continue
        out.append(s)
    return out


def _month_end_date(period_mmYYYY: str) -> str:
    mm, yyyy = period_mmYYYY.split(".")
    m = int(mm)
    y = int(yyyy)
    last_day = calendar.monthrange(y, m)[1]
    return f"{last_day:02d}.{m:02d}.{y}"


# ---------------------------
# Patterns
# ---------------------------

# Month header:
#   "Ноябрь 2023 года"
#   "Ноябрь 2023"
_MONTH_HDR_RE = re.compile(
    r"^(Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Октябрь|Ноябрь|Декабрь)\s+(\d{4})(?:\s+года)?$",
    re.IGNORECASE,
)

_MONTHS = {
    "январь": "01",
    "февраль": "02",
    "март": "03",
    "апрель": "04",
    "май": "05",
    "июнь": "06",
    "июль": "07",
    "август": "08",
    "сентябрь": "09",
    "октябрь": "10",
    "ноябрь": "11",
    "декабрь": "12",
}

# Tables contain:
#  - posting/correction lines: "MM.YYYY <amount>"
#  - payment lines: "DD.MM.YYYY <amount>"
_PERIOD_RE = re.compile(r"^(\d{2}\.\d{4})$")
_DATE_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})$")

_CHARGE_INLINE_RE = re.compile(r"^(\d{2}\.\d{4})\s+(.+)$")
_PAYMENT_INLINE_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(.+)$")

# Annual adjustment block (kept as-is)
_ADJ_START_RE = re.compile(r"^Доля от размера\b", re.IGNORECASE)
_ADJ_YEAR_RE = re.compile(r"по итогам\s+(\d{4})\s+года\b", re.IGNORECASE)
_ADJ_PAYABLE_RE = re.compile(r"подлежащая оплате в\s+([а-я]+)\s+(\d{4})", re.IGNORECASE)

_PAYABLE_MONTHS = {
    "январе": "01",
    "феврале": "02",
    "марте": "03",
    "апреле": "04",
    "мае": "05",
    "июне": "06",
    "июле": "07",
    "августе": "08",
    "сентябре": "09",
    "октябре": "10",
    "ноябре": "11",
    "декабре": "12",
}

_TOTAL_HDR_RE = re.compile(r"^ИТОГО ПО ПЕРИОДУ\b", re.IGNORECASE)


# ---------------------------
# Main
# ---------------------------


def _money_only_line_value(ln: str) -> Optional[str]:
    """
    Return normalized money string if the line contains exactly ONE money token
    and nothing else (except spaces/nbsp).
    Otherwise return None.

    Needed to detect broken totals rows like:
      "1 242 526.53"
      "0.00"
    """
    ln = (ln or "").strip()
    if not ln:
        return None
    # reuse same guards as _try_money_values (dates/time already excluded there)
    vals = _try_money_values(ln)
    if len(vals) != 1:
        return None

    # If after removing money tokens only whitespace remains -> "money-only line"
    rest = _MONEY_TOKEN_RE.sub("", ln)
    rest = rest.replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
    if rest == "":
        return vals[0]
    return None


def _premerge_table_tokens(lines: List[str]) -> List[str]:
    """
    Normalize MOEK statement table text stream.

    Some PDFs emit table columns as separate lines, e.g.:
      05.2024
      712 954.13
      18.07.2019
      -5 088.06
    or month totals as 2-3 consecutive "money-only" lines:
      455 891.23
      457 286.42
      1 395.19

    This function deterministically merges:
      - (period OR date) + next money-only line  -> single logical line "X Y"
      - runs of 2-3 consecutive money-only lines -> single logical line "A B [C]"

    It does NOT use heuristics; it only relies on strict token patterns.
    """
    out: List[str] = []
    i = 0
    n = len(lines)

    def _next_nonempty(j: int) -> Tuple[int, Optional[str]]:
        while j < n:
            s = (lines[j] or "").strip()
            if s:
                return j, s
            j += 1
        return n, None

    while i < n:
        s = (lines[i] or "").strip()
        if not s:
            i += 1
            continue

        # Merge (date|period) + money
        j, nxt = _next_nonempty(i + 1)
        if nxt is not None:
            if (_DATE_RE.match(s) or _PERIOD_RE.match(s)) and _money_only_line_value(
                nxt
            ) is not None:
                out.append(f"{s} {nxt}")
                i = j + 1
                continue

        # Merge short runs of money-only lines (2-3)
        if _money_only_line_value(s) is not None:
            run = [s]
            j = i + 1
            while len(run) < 3:
                k, nxt2 = _next_nonempty(j)
                if nxt2 is None:
                    break
                if _money_only_line_value(nxt2) is None:
                    break
                run.append(nxt2)
                j = k + 1

            if len(run) >= 2:
                out.append(" ".join(run))
                i = j
                continue

        out.append(s)
        i += 1

    return out


def parse_tables(lines: List[str]) -> Tuple[List[Dict], List[Dict]]:
    """
    Extract charges and payments from tables.

    Critical domain rules (MOEK "Справка о задолженности"):
      - Accrual PERIOD is the month header ("Ноябрь 2023 года"), not inner MM.YYYY rows.
      - Inner MM.YYYY rows represent posting/correction months for the SAME accrual period.
      - The month block contains an unlabelled TOTAL 'charged' (and also total 'paid' and 'debt').

    Validations requested:
      A) Month validation:
         base_posting (MM.YYYY == header period) + sum(corrections) == month_total_charged
      B) Document totals validation:
         sum(month_totals) == totals in "ИТОГО ПО ПЕРИОДУ" (charged/paid/debt)

    NOTE:
      This module has no warnings channel; discrepancies are signalled via ValueError.
    """
    lines = _premerge_table_tokens(lines)

    charges: List[Dict] = []
    payments: List[Dict] = []

    n = len(lines)
    i = 0

    # Count only "footer-like" dates: a date line NOT followed by a money amount soon.
    date_counts: Dict[str, int] = {}
    for idx, s in enumerate(lines):
        ss = (s or "").strip()
        if not ss:
            continue
        mdt = _DATE_RE.match(ss)
        if not mdt:
            continue
        dt0 = mdt.group(0)

        # If the next non-empty lines contain money, it's almost certainly a payment row, not a footer.
        looks_like_payment = False
        for j in range(idx + 1, min(n, idx + 4)):
            nxt = (lines[j] or "").strip()
            if not nxt:
                continue
            if _try_money_line(nxt) is not None:
                looks_like_payment = True
            break

        if not looks_like_payment:
            date_counts[dt0] = date_counts.get(dt0, 0) + 1

    footer_date: Optional[str] = None
    if date_counts:
        dt0, cnt = max(date_counts.items(), key=lambda kv: kv[1])
        # 3+ occurrences strongly indicates repeated footer print date (>= 3 pages or duplicated footer)
        if cnt >= 3:
            footer_date = dt0

    current_month: Optional[str] = None

    # pending rows encountered BEFORE month header in the text stream
    # kind == "payment": (kind, date_ddmmyyyy, amount_str)
    # kind == "charge":  (kind, src_period_mmYYYY, amount_str)
    pending_rows: List[Tuple[str, str, str]] = []

    # NEW: queue for \"column-separated\" payments inside a month.
    # Some PDFs emit all dates first, then all amounts; we reconstruct payments FIFO.
    pending_payment_dates: List[str] = []
    payment_fifo_mode: bool = (
        False  # включаем только когда реально видим "колонку дат" без сумм
    )

    # annual adjustment parsing (kept)
    adj_mode: bool = False
    adj_year: Optional[str] = None
    adj_payable_month: Optional[str] = None
    adj_base_period_last: Optional[str] = None

    def build_adj_fields(base_period: Optional[str]) -> Dict:
        out: Dict = {"kind": "annual_adjustment_share"}
        if adj_year:
            out["adjustment_year"] = int(adj_year)
        if adj_payable_month:
            out["payable_month"] = adj_payable_month
        if base_period:
            out["base_period"] = base_period
        return out

    # --- per-month accumulators (to pick correct totals deterministically by "numbers must match") ---
    month_base_posting: Dict[str, Decimal] = {}
    month_corr_sum: Dict[str, Decimal] = {}
    month_payments_sum: Dict[str, Decimal] = {}

    # candidates captured as "standalone money values" inside each month block
    month_money_candidates: Dict[str, List[Decimal]] = {}

    month_money_groups: Dict[str, List[List[Decimal]]] = {}

    # resolved month totals (final):
    month_total_charged: Dict[str, Decimal] = {}
    month_total_paid: Dict[str, Decimal] = {}
    month_total_debt: Dict[str, Decimal] = {}

    def _push_candidate(mny: Decimal) -> None:
        if not current_month:
            return
        month_money_candidates.setdefault(current_month, []).append(mny)

    def _add_payment(amount: Decimal) -> None:
        # By design, call only when current_month exists
        if not current_month:
            raise ValueError("internal: _add_payment called without current_month")
        month_payments_sum[current_month] = (
            month_payments_sum.get(current_month, Decimal("0.00")) + amount
        )

    def _effective_paid_sum_for_month(month: str) -> Decimal:
        """
        Net paid sum for month after canceling opposite-sign pairs (+X/-X)
        with the same date and the same absolute amount.
        """
        rows: List[Tuple[str, Decimal]] = []
        for p in payments:
            if p.get("kind") == "annual_adjustment_share":
                continue
            if p.get("period") != month:
                continue
            dt = p.get("date")
            if not dt:
                continue
            try:
                amt = _d(str(p.get("amount")))
            except Exception:
                continue
            rows.append((dt, amt))

        # count by (date, abs(amount))
        cnt: Dict[Tuple[str, Decimal], Dict[str, int]] = {}
        for dt, amt in rows:
            key = (dt, abs(amt).quantize(TOL))
            if key not in cnt:
                cnt[key] = {"pos": 0, "neg": 0}
            if amt >= Decimal("0.00"):
                cnt[key]["pos"] += 1
            else:
                cnt[key]["neg"] += 1

        total = Decimal("0.00")
        for (_dt, abs_amt), c in cnt.items():
            k = min(c["pos"], c["neg"])
            rem_pos = c["pos"] - k
            rem_neg = c["neg"] - k
            if rem_pos:
                total += abs_amt * Decimal(rem_pos)
            if rem_neg:
                total -= abs_amt * Decimal(rem_neg)

        return total.quantize(TOL)

    def _add_posting(period_mmYYYY: str, amount: Decimal) -> None:
        # By design, call only when current_month exists
        if not current_month:
            raise ValueError("internal: _add_posting called without current_month")

        if period_mmYYYY == current_month:
            month_base_posting[current_month] = (
                month_base_posting.get(current_month, Decimal("0.00")) + amount
            )
        else:
            month_corr_sum[current_month] = (
                month_corr_sum.get(current_month, Decimal("0.00")) + amount
            )

    def _finalize_month(prev_month: Optional[str]) -> None:
        if not prev_month:
            return

        base = month_base_posting.get(prev_month, Decimal("0.00")).quantize(TOL)
        corr = month_corr_sum.get(prev_month, Decimal("0.00")).quantize(TOL)
        paid = month_payments_sum.get(prev_month, Decimal("0.00")).quantize(TOL)

        want_charged = (base + corr).quantize(TOL)
        want_debt = (want_charged - paid).quantize(TOL)

        cands = month_money_candidates.get(prev_month, [])
        uniq: List[Decimal] = []

        for x in cands:
            if all(not _close(x, y) for y in uniq):
                uniq.append(x)

        # 1) charged total MUST exist as a number in block candidates (strict)
        charged_matches = [x for x in uniq if _close(x, want_charged)]
        if not charged_matches:
            raise UserFacingError(
                code="MONTH_TOTAL_NOT_FOUND",
                stage="pdf_to_json",
                message=(
                    f"Ошибка разбора справки: не найден итог начислений за {prev_month}. "
                    "Сумма (начислено + корректировка) не найдена среди итогов за месяц в справке."
                ),
                details={
                    "period": prev_month,
                    "charged_base": str(base),
                    "charged_correction": str(corr),
                    "expected_month_total": str(want_charged),
                    "block_total_candidates": [str(x) for x in uniq[:50]],
                },
            )

        charged_total = sorted(charged_matches)[0]
        month_total_charged[prev_month] = charged_total

        groups = month_money_groups.get(prev_month, [])

        # 2) paid/debt totals:
        # Source of truth for month paid/debt is the PRINTED totals inside the month block.
        # Dated payment rows (paid sum) may be incomplete in some PDFs.
        paid_total: Optional[Decimal] = None
        debt_total: Optional[Decimal] = None

        # A1 guard (format variant):
        # Some statements print month tail as:
        #   X            (charged total)
        #   X 0.00       (debt total; paid = 0.00)
        # Our pre-merge may also create a synthetic triple [X, X, 0.00],
        # which would look like "paid = charged" if accepted.
        # Deterministic rule: if an explicit pair [X, 0.00] exists (in any order),
        # prefer it over the synthetic triple [X, X, 0.00].
        has_pair_charged_zero = False
        for g in groups:
            if len(g) == 2:
                a, b = g[0], g[1]
                if (_close(a, charged_total) and _close(b, Decimal("0.00"))) or (
                    _close(b, charged_total) and _close(a, Decimal("0.00"))
                ):
                    has_pair_charged_zero = True
                    break

        # 2.1) Prefer explicit totals from printed grouped lines.
        # In MOEK statements the month totals line is printed as:
        #   charged, paid, debt  (in this order).
        # We do NOT swap columns; we only accept the triple if it satisfies identity.
        for g in groups:
            if len(g) == 3 and _close(g[0], charged_total):
                # A1: skip synthetic triple [charged, charged, 0.00] if explicit pair [charged, 0.00] exists
                if (
                    has_pair_charged_zero
                    and _close(g[1], charged_total)
                    and _close(g[2], Decimal("0.00"))
                ):
                    continue

                p = g[1]
                d = g[2]
                if _close((p + d).quantize(TOL), charged_total):
                    paid_total = p
                    debt_total = d
                    break

        # Pair [charged, paid] is unambiguous.
        if paid_total is None:
            for g in groups:
                if len(g) == 2 and _close(g[0], charged_total):
                    paid_total = g[1]
                    debt_total = (charged_total - paid_total).quantize(TOL)
                    break

        # 2.2) If no explicit group found, reconstruct from uniq via identity:
        # charged_total = paid_total + debt_total, both numbers must be present in uniq.
        # If we have dated payments (paid != 0), prefer the orientation that matches want_debt
        # (charged - paid(rows)) rather than matching paid itself.
        if paid_total is None or debt_total is None:
            pair_found: Optional[Tuple[Decimal, Decimal]] = None

            # Build all valid identity pairs (a + b == charged_total), where both are printed candidates.
            valid_pairs: List[Tuple[Decimal, Decimal]] = []
            for a in uniq:
                if a < Decimal("0.00") or a > charged_total:
                    continue
                b = (charged_total - a).quantize(TOL)
                if any(_close(x, b) for x in uniq):
                    valid_pairs.append((a, b))

            if paid != Decimal("0.00"):
                # 1) Prefer pair where debt matches want_debt
                for a, b in valid_pairs:
                    # orientation (paid=a, debt=b)
                    if _close(b, want_debt):
                        pair_found = (a, b)
                        break
                    # orientation (paid=b, debt=a)
                    if _close(a, want_debt):
                        pair_found = (b, a)
                        break

                # 2) Otherwise prefer paid == charged - want_debt (still derived from rows)
                if pair_found is None:
                    target_paid = (charged_total - want_debt).quantize(TOL)
                    for a, b in valid_pairs:
                        if _close(a, target_paid):
                            pair_found = (a, b)
                            break
                        if _close(b, target_paid):
                            pair_found = (b, a)
                            break

                # 3) Only as a last resort, try to match sum of dated payments directly
                if pair_found is None:
                    for a, b in valid_pairs:
                        if _close(a, paid):
                            pair_found = (a, b)
                            break
                        if _close(b, paid):
                            pair_found = (b, a)
                            break
            else:
                # No dated payments:
                # Deterministic rule for MOEK month blocks:
                # if 0.00 is present among printed candidates, treat it as PAID=0.00 (not DEBT=0.00),
                # because payments for a zero-paid month are allocated to other obligations.
                if valid_pairs:
                    zero = Decimal("0.00")
                    has_zero = any(_close(x, zero) for x in uniq)
                    if has_zero:
                        # prefer (paid=0.00, debt=charged_total) when available
                        for a, b in valid_pairs:
                            if _close(a, zero):
                                pair_found = (a, b)
                                break
                            if _close(b, zero):
                                # valid pair is (charged_total, 0.00) -> interpret as paid=0.00, debt=charged_total
                                pair_found = (zero, a)
                                break

                    if pair_found is None:
                        pair_found = valid_pairs[0]

            if pair_found:
                paid_total, debt_total = pair_found

        # 2.3) If we have dated payments, we can optionally "snap" paid_total to them when it matches.
        # (Do NOT force match; only use as a confirmation.)
        if paid != Decimal("0.00") and paid_total is not None:
            if _close(paid_total, paid):
                pass  # ok
            elif debt_total is not None and _close(
                (charged_total - debt_total).quantize(TOL), paid
            ):
                paid_total = paid
                # keep debt_total as printed/derived; coherence checks below will verify

        # 3) Debt fallback: if still missing, try matching expected debt (only meaningful when paid rows exist)
        if debt_total is None:
            if paid_total is not None:
                debt_total = (charged_total - paid_total).quantize(TOL)
            elif paid != Decimal("0.00"):
                debt_matches = [x for x in uniq if _close(x, want_debt)]
                if debt_matches:
                    debt_total = sorted(debt_matches)[0]

        # 4) Finalize: both must exist (no silent guessing beyond identity)
        if paid_total is None:
            raise UserFacingError(
                code="MONTH_PAID_TOTAL_NOT_FOUND",
                stage="pdf_to_json",
                message=(
                    f"Ошибка разбора справки: не найден итог оплат за {prev_month}. "
                    "Сумма оплат по строкам рассчитана, но итог оплаты за месяц не найден среди итогов справки."
                ),
                details={
                    "period": prev_month,
                    "payments_sum": str(paid),
                    "block_total_candidates": [str(x) for x in uniq[:50]],
                },
            )

        if debt_total is None:
            raise UserFacingError(
                code="MONTH_DEBT_TOTAL_NOT_FOUND",
                stage="pdf_to_json",
                message=(
                    f"Ошибка разбора справки: не найден итог задолженности за {prev_month}. "
                    "Задолженность рассчитана как (начислено − оплачено), но итог долга за месяц не найден среди итогов справки."
                ),
                details={
                    "period": prev_month,
                    "charged_total": str(charged_total),
                    "paid_total": str(paid_total),
                    "block_total_candidates": [str(x) for x in uniq[:50]],
                },
            )

        month_total_paid[prev_month] = paid_total
        month_total_debt[prev_month] = debt_total

        # 5) Keep strict month charge validation (as before)
        if not _close(charged_total, want_charged):
            raise ValueError(
                f"month charge validation failed for {prev_month}: "
                f"base({base}) + corr({corr}) = {want_charged}, but month_total={charged_total}"
            )

        # 6) Coherence validation:
        # - if we have dated payments rows, validate against want_debt (charged - payments_sum)
        # - if no dated payments rows, validate against printed debt_total
        expected_debt_from_totals = (charged_total - paid_total).quantize(TOL)

        # Always validate against printed debt_total (it is the month block total).
        # paid_rows (sum of dated payments) can be incomplete / shifted in text layer.
        if not _close(expected_debt_from_totals, debt_total):
            raise ValueError(
                f"month totals coherence failed for {prev_month}: "
                f"charged({charged_total}) - paid({paid_total}) != debt_total(printed)({debt_total})"
            )

    # --- document totals from "ИТОГО ПО ПЕРИОДУ" ---
    doc_total_charged: Optional[Decimal] = None
    doc_total_paid: Optional[Decimal] = None
    doc_total_debt: Optional[Decimal] = None

    def _parse_doc_totals_from(
        i_start: int,
    ) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """
        MOEK PDFs often have "ИТОГО ПО ПЕРИОДУ" totals split across several lines
        and may repeat the same amounts multiple times.
        Old logic ("first 3 money tokens") is too brittle and may pick wrong columns.

        Strategy:
          1) Collect up to ~10 money values from next few lines.
          2) Choose the best (charged, paid, debt) triple minimizing |charged - paid - debt|.
          3) If no good triple found, fallback to first 3 values.
        """
        found: List[Decimal] = []
        j = i_start

        # collect money tokens from next lines (bounded)
        max_lines = 10
        max_vals = 10
        lines_seen = 0
        while j < n and lines_seen < max_lines and len(found) < max_vals:
            ln2 = (lines[j] or "").strip()
            vals = _try_money_values(ln2)
            for s in vals:
                try:
                    found.append(_d(s).quantize(TOL))
                except Exception:
                    continue
                if len(found) >= max_vals:
                    break
            j += 1
            lines_seen += 1

        if len(found) < 3:
            return None, None, None

        # Prefer a triple that satisfies charged - paid ≈ debt.
        best: Tuple[Decimal, Decimal, Decimal] | None = None
        best_score: Tuple[Decimal, Decimal, Decimal] | None = (
            None  # (residual, |paid|, -charged)
        )

        for a in found:
            for b in found:
                for c in found:
                    resid = (a - b - c).copy_abs().quantize(TOL)
                    score = (
                        resid,
                        b.copy_abs().quantize(TOL),
                        (Decimal("0.00") - a).quantize(TOL),
                    )
                    if best is None or score < best_score:  # type: ignore[operator]
                        best = (a, b, c)
                        best_score = score

        # Accept only if residual is within a few cents.
        if best is not None and best_score is not None:
            if best_score[0] <= Decimal("0.02"):
                return best[0], best[1], best[2]

        # Fallback: first 3 values (legacy behavior)
        return found[0], found[1], found[2]

    # ---------------------------
    # Main scan
    # ---------------------------
    while i < n:
        ln = (lines[i] or "").strip()

        # Month header
        mh = _MONTH_HDR_RE.match(ln)
        if mh:
            prev = current_month
            if prev is not None:
                month_payments_sum[prev] = _effective_paid_sum_for_month(prev)
                _finalize_month(prev)

            mon = mh.group(1).lower()
            yyyy = mh.group(2)
            mm = _MONTHS.get(mon)
            current_month = f"{mm}.{yyyy}" if mm else None

            # Apply deferred rows to this month (now we have current_month)
            if pending_rows and current_month:
                for kind, a, amt_str in pending_rows:
                    amt = Decimal(amt_str).quantize(TOL)
                    if kind == "payment":
                        # a = date
                        payments.append(
                            {"date": a, "amount": f"{amt:.2f}", "period": current_month}
                        )
                        _add_payment(amt)
                    elif kind == "charge":
                        # a = src posting period MM.YYYY
                        _add_posting(a, amt)
                        _push_candidate(amt)
                pending_rows.clear()

            # reset month-local queues
            pending_payment_dates.clear()
            payment_fifo_mode = False

            # reset AA block on new month
            adj_mode = False
            adj_year = None
            adj_payable_month = None
            adj_base_period_last = None

            i += 1
            continue

        # Annual adjustment start
        if _ADJ_START_RE.match(ln):
            # AA header can be split across many lines; capture until AA data begins (MM.YYYY) or new month header.
            tail_parts = [ln]
            j = i + 1
            while j < n and len(tail_parts) < 20:
                nxt = (lines[j] or "").strip()
                if not nxt:
                    j += 1
                    continue
                if (
                    _PERIOD_RE.fullmatch(nxt)
                    or _MONTH_HDR_RE.match(nxt)
                    or _TOTAL_HDR_RE.match(nxt)
                ):
                    break
                tail_parts.append(nxt)
                j += 1
            tail = " ".join(tail_parts)
            my = _ADJ_YEAR_RE.search(tail)
            mp = _ADJ_PAYABLE_RE.search(tail)
            if my and mp:
                adj_year = my.group(1)
                word = mp.group(1).lower()
                yyyy = mp.group(2)
                mm = _PAYABLE_MONTHS.get(word)
                if mm:
                    adj_payable_month = f"{mm}.{yyyy}"
                    adj_mode = True
                    adj_base_period_last = None
            i += 1
            continue

        # Document totals header
        if _TOTAL_HDR_RE.match(ln):
            a, b, c = _parse_doc_totals_from(i + 1)
            doc_total_charged, doc_total_paid, doc_total_debt = a, b, c
            i += 1
            continue

        # Payment inline "DD.MM.YYYY amount"
        mpay = _PAYMENT_INLINE_RE.match(ln)
        if mpay:
            dt = mpay.group(1)
            amt_s = _try_money_line(mpay.group(2))
            if amt_s is not None:
                amt = _d(amt_s)
                item: Dict = {"date": dt, "amount": f"{amt:.2f}"}
                if adj_mode:
                    item.update(build_adj_fields(adj_base_period_last))
                    payments.append(item)
                else:
                    if current_month:
                        item["period"] = current_month
                        payments.append(item)
                        _add_payment(amt)
                    else:
                        pending_rows.append(("payment", dt, f"{amt:.2f}"))
            i += 1
            continue

        # Charge posting inline "MM.YYYY amount"
        mch = _CHARGE_INLINE_RE.match(ln)
        if mch:
            period = mch.group(1)
            amt_s = _try_money_line(mch.group(2))
            if amt_s is not None:
                amt = _d(amt_s)
                if adj_mode:
                    item = {"period": period, "amount": f"{amt:.2f}"}
                    adj_base_period_last = period
                    item.update(build_adj_fields(period))
                    charges.append(item)
                else:
                    if current_month:
                        _add_posting(period, amt)
                        _push_candidate(amt)
                    else:
                        # defer posting row until month header appears
                        pending_rows.append(("charge", period, f"{amt:.2f}"))
            i += 1
            continue

        # Column payment: date line + money on next lines
        if _DATE_RE.match(ln) and current_month:
            amt_s = None

            # Allow crossing page breaks; stop only on logical block boundaries.
            # Keep a sane cap to avoid runaway on corrupted text layers.
            MAX_LOOKAHEAD = 200

            for k in range(i + 1, min(n, i + 1 + MAX_LOOKAHEAD)):
                ln2 = (lines[k] or "").strip()
                if not ln2:
                    continue

                # Stop on logical boundaries: next month / period marker / document totals
                if (
                    _MONTH_HDR_RE.match(ln2)
                    or _PERIOD_RE.match(ln2)
                    or ln2.upper().startswith("ИТОГО ПО ПЕРИОДУ")
                ):
                    break

                # Optional: if another date appears before any amount, treat this date as footer/noise.
                # (Prevents "print date" from stealing an amount much later.)
                if _DATE_RE.match(ln2):
                    # Column-separated payments: dates go as a block (no amounts nearby).
                    # Enqueue current date and enable FIFO-mode for this month.
                    if not (footer_date and ln == footer_date):
                        pending_payment_dates.append(ln)
                        payment_fifo_mode = True
                    amt_s = None
                    break

                vals = _try_money_values(ln2)

                # If a line contains 2+ money tokens, it's a totals row (charged/paid/debt),
                # not a single payment amount. Stop lookahead so this date doesn't "steal" totals.
                if len(vals) >= 2:
                    amt_s = None
                    break

                cand = vals[0] if len(vals) == 1 else _try_money_line(ln2)
                if cand is not None:
                    # --- NEW: prevent stealing broken totals rows (amount / amount / amount without date) ---
                    # If current candidate line is "money-only" and the next significant line is also money-only
                    # (or has 2+ money tokens), treat this as a broken totals row, not a payment amount.
                    if _money_only_line_value(ln2) is not None:
                        for j in range(k + 1, min(n, k + 1 + 20)):
                            ln3 = (lines[j] or "").strip()
                            if not ln3:
                                continue

                            # stop peeking on logical boundaries; we only care about immediate structure
                            if (
                                _MONTH_HDR_RE.match(ln3)
                                or _PERIOD_RE.match(ln3)
                                or ln3.upper().startswith("ИТОГО ПО ПЕРИОДУ")
                                or _DATE_RE.match(ln3)
                            ):
                                break

                            vals3 = _try_money_values(ln3)
                            if (
                                len(vals3) >= 2
                                or _money_only_line_value(ln3) is not None
                            ):
                                amt_s = None
                                cand = None
                            break

                        if cand is None:
                            break

                    # Domain: payment rows cannot be 0.00. If we hit 0.00 near the date, treat as noise and stop.
                    if _close(_d(cand), Decimal("0.00")):
                        amt_s = None
                        break

                    amt_s = cand
                    break

            # If this is footer_date and no amount was found nearby, treat as footer/noise
            if footer_date and ln == footer_date and amt_s is None:
                i += 1
                continue

            if amt_s is not None:
                amt = _d(amt_s)
                item: Dict = {"date": ln, "amount": f"{amt:.2f}"}
                if adj_mode:
                    item.update(build_adj_fields(adj_base_period_last))
                    payments.append(item)
                else:
                    if current_month:
                        item["period"] = current_month
                        payments.append(item)
                        _add_payment(amt)
                    else:
                        pending_rows.append(("payment", ln, f"{amt:.2f}"))

            i += 1
            continue

        # Column charge posting: period line + money on next lines
        if _PERIOD_RE.match(ln):
            period = ln
            amt_s = None
            for k in range(i + 1, min(n, i + 10)):
                cand = _try_money_line((lines[k] or "").strip())
                if cand is not None:
                    amt_s = cand
                    break
            if amt_s is not None:
                amt = _d(amt_s)
                if adj_mode:
                    item = {"period": period, "amount": f"{amt:.2f}"}
                    adj_base_period_last = period
                    item.update(build_adj_fields(period))
                    charges.append(item)
                else:
                    if current_month:
                        _add_posting(period, amt)
                        _push_candidate(amt)
                    else:
                        pending_rows.append(("charge", period, f"{amt:.2f}"))
            i += 1
            continue

        # Standalone money inside current month block
        # IMPORTANT: some PDFs place TWO totals on one line: "<charged> <paid>".
        # We must capture ALL amounts from that line.
        vals = _try_money_values(ln)
        if vals:
            decs = [_d(s) for s in vals]
            # NEW: If we have pending payment dates and this line is a money-only line
            # with a single amount, treat it as the amount for the earliest queued date (FIFO).
            # This fixes cases where the PDF text layer outputs a "dates column" block
            # followed by an "amounts column" block.
            if (
                current_month
                and (not adj_mode)
                and pending_payment_dates
                and len(decs) == 1
            ):
                mv = _money_only_line_value(ln)
                if mv is not None:
                    amt = _d(mv)

                    # Domain: payment rows cannot be 0.00
                    if _close(amt, Decimal("0.00")):
                        pass
                    else:
                        # NEW GUARD:
                        # If ближайше по потоку (до границы месяца/периода/следующей даты)
                        # встречается строка с 2+ суммами, значит мы уже в зоне итогов (charged/paid/debt),
                        # и текущая "одиночная сумма" НЕ должна привязываться к дате FIFO.
                        looks_like_totals_ahead = False
                        LOOKAHEAD = 80

                        for j in range(i + 1, min(n, i + 1 + LOOKAHEAD)):
                            ln2 = (lines[j] or "").strip()
                            if not ln2:
                                continue

                            # stop on logical boundaries; totals for month end are before these boundaries
                            if (
                                _MONTH_HDR_RE.match(ln2)
                                or _PERIOD_RE.match(ln2)
                                or _TOTAL_HDR_RE.match(ln2)
                                or ln2.upper().startswith("ИТОГО ПО ПЕРИОДУ")
                                or _DATE_RE.match(ln2)
                            ):
                                break

                            vals2 = _try_money_values(ln2)
                            if len(vals2) >= 2:
                                looks_like_totals_ahead = True
                                break

                        if not looks_like_totals_ahead:
                            # OK: это похоже на реальную "колонку сумм" платежей
                            dt = pending_payment_dates.pop(0)
                            payments.append(
                                {
                                    "date": dt,
                                    "amount": f"{amt:.2f}",
                                    "period": current_month,
                                }
                            )
                            _add_payment(amt)
                            i += 1
                            continue
                        else:
                            # Впереди видны итоги месяца (строка с 2+ суммами) — значит,
                            # текущая одиночная сумма относится к итогам (charged/paid/debt),
                            # а НЕ к платежу. Скорее всего queued dates — это дата печати/подвал.
                            pending_payment_dates.clear()
                            payment_fifo_mode = False
                            # НЕ consuming line: пусть дальше обработается как кандидат/итог
                            # (ниже по коду эта сумма будет добавлена в month_money_candidates/groups)

            # сохраняем группой, если в строке 2+ сумм (итоги)
            if len(decs) >= 2 and current_month:
                month_money_groups.setdefault(current_month, []).append(decs)
            # и как раньше — пушим каждую сумму в кандидаты
            for x in decs:
                _push_candidate(x)
            i += 1
            continue

        i += 1

    # finalize last month
    if current_month is not None:
        month_payments_sum[current_month] = _effective_paid_sum_for_month(current_month)
    _finalize_month(current_month)

    # Build final ordinary charges: one per month header
    for m in sorted(month_total_charged.keys()):
        charges.append({"period": m, "amount": f"{month_total_charged[m]:.2f}"})

    if not charges:
        raise UserFacingError(
            code="CHARGES_TABLE_NOT_FOUND",
            stage="pdf_to_json",
            message=(
                "Ошибка разбора справки: не найдены начисления. "
                "Сервис не смог выделить таблицу начислений из PDF."
            ),
            details={},
        )

    # Document totals validation
    if (
        doc_total_charged is not None
        and doc_total_paid is not None
        and doc_total_debt is not None
    ):

        # Include annual_adjustment_share into document totals (MOEK prints it inside "ИТОГО ПО ПЕРИОДУ")
        aa_charged = Decimal("0.00")
        aa_paid = Decimal("0.00")

        for c in charges:
            if c.get("kind") == "annual_adjustment_share":
                try:
                    aa_charged += Decimal(
                        str(c.get("amount")).replace(" ", "").replace(",", ".")
                    )
                except Exception:
                    pass

        for p in payments:
            if p.get("kind") == "annual_adjustment_share":
                try:
                    aa_paid += Decimal(
                        str(p.get("amount")).replace(" ", "").replace(",", ".")
                    )
                except Exception:
                    pass

        sum_ch = (
            sum(month_total_charged.values(), Decimal("0.00")) + aa_charged
        ).quantize(TOL)
        sum_pd = (sum(month_total_paid.values(), Decimal("0.00")) + aa_paid).quantize(
            TOL
        )
        sum_db = (
            sum(month_total_debt.values(), Decimal("0.00")) + (aa_charged - aa_paid)
        ).quantize(TOL)

        aa_charged = aa_charged.quantize(TOL)
        aa_paid = aa_paid.quantize(TOL)

        # --- FIX: guard against swapped paid/debt in "ИТОГО ПО ПЕРИОДУ" ---
        # Sometimes both permutations satisfy charged - paid - debt == 0,
        # so the earlier selection logic may choose paid/debt reversed.
        # If period sums clearly match the opposite mapping, swap them.

        if (
            doc_total_charged is not None
            and doc_total_paid is not None
            and doc_total_debt is not None
        ):
            if (
                (
                    not _close(sum_pd, doc_total_paid)
                    or not _close(sum_db, doc_total_debt)
                )
                and _close(sum_pd, doc_total_debt)
                and _close(sum_db, doc_total_paid)
                and _close(
                    (doc_total_paid + doc_total_debt).quantize(TOL),
                    doc_total_charged,
                )
            ):
                doc_total_paid, doc_total_debt = doc_total_debt, doc_total_paid

        if not _close(sum_ch, doc_total_charged):
            raise UserFacingError(
                code="DOC_TOTALS_MISMATCH_CHARGED",
                stage="pdf_to_json",
                message=(
                    "Ошибка проверки справки: не сошлись итоги по начислению. "
                    "Сумма начислений по периодам не равна значению в строке «ИТОГО ПО ПЕРИОДУ»."
                ),
                details={
                    "sum_periods_charged": str(sum_ch),
                    "doc_total_charged": str(doc_total_charged),
                    "hint": "Проверь таблицу начислений по периодам и строку «ИТОГО ПО ПЕРИОДУ» в PDF.",
                },
            )

        if not _close(sum_pd, doc_total_paid):
            delta = (sum_pd - doc_total_paid).quantize(TOL)

            # Deterministic repair for A1-like months:
            # Some PDFs print month tail as a synthetic triple [charged, charged, 0.00].
            # When there are NO ordinary payment rows (paid_rows=0), this must be interpreted as
            # paid=0.00 and debt=charged (payments are only present as annual_adjustment_share).
            # If a subset of such months exactly explains the document-level paid delta, flip them.
            if delta > Decimal("0.00"):
                flip_months: List[Tuple[str, Decimal]] = []
                for m in sorted(month_total_charged.keys()):
                    ch = month_total_charged.get(m, Decimal("0.00")).quantize(TOL)
                    pd = month_total_paid.get(m, Decimal("0.00")).quantize(TOL)
                    db = month_total_debt.get(m, Decimal("0.00")).quantize(TOL)
                    pd_rows = month_payments_sum.get(m, Decimal("0.00")).quantize(TOL)
                    if (
                        _close(pd_rows, Decimal("0.00"))
                        and _close(pd, ch)
                        and _close(db, Decimal("0.00"))
                        and ch > Decimal("0.00")
                    ):
                        flip_months.append((m, ch))

                def _cents(x: Decimal) -> int:
                    return int((x * 100).to_integral_value(rounding=ROUND_HALF_UP))

                target = _cents(delta.copy_abs())
                dp: Dict[int, List[str]] = {0: []}  # sum_cents -> months
                for m, ch in sorted(flip_months, key=lambda t: (-t[1], t[0])):
                    val = _cents(ch)
                    new = dict(dp)
                    for s, picked in dp.items():
                        ns = s + val
                        if ns > target or ns in new:
                            continue
                        new[ns] = picked + [m]
                        if ns == target:
                            break
                    dp = new
                    if target in dp:
                        break

                if target in dp and dp[target]:
                    for m in dp[target]:
                        month_total_paid[m] = Decimal("0.00")
                        month_total_debt[m] = month_total_charged[m].quantize(TOL)

                    # recompute sums after flips (AA is included separately)
                    sum_pd = (
                        sum(month_total_paid.values(), Decimal("0.00")) + aa_paid
                    ).quantize(TOL)
                    sum_db = (
                        sum(month_total_debt.values(), Decimal("0.00"))
                        + (aa_charged - aa_paid)
                    ).quantize(TOL)
                    delta = (sum_pd - doc_total_paid).quantize(TOL)

            if _close(sum_pd, doc_total_paid):
                # repaired deterministically via month flips
                pass
            else:
                # Build per-month breakdown so we can see which month(s) cause the delta.
                rows: List[Tuple[str, Decimal, Decimal, Decimal, Decimal]] = []
                for m in sorted(month_total_charged.keys()):
                    ch = month_total_charged.get(m, Decimal("0.00")).quantize(TOL)
                    pd = month_total_paid.get(m, Decimal("0.00")).quantize(TOL)
                    db = month_total_debt.get(m, Decimal("0.00")).quantize(TOL)
                    pd_rows = month_payments_sum.get(m, Decimal("0.00")).quantize(TOL)
                    rows.append((m, ch, pd, db, pd_rows))

                # Suspicion score: inconsistency inside month, plus divergence from dated payment rows if present
                def _score(
                    r: Tuple[str, Decimal, Decimal, Decimal, Decimal],
                ) -> Decimal:
                    _m, ch, pd, db, pd_rows = r
                    implied_db = (ch - pd).quantize(TOL)
                    score = (implied_db - db).copy_abs()
                    if pd_rows != Decimal("0.00"):
                        score += (pd - pd_rows).copy_abs()
                    return score

                rows_sorted = sorted(rows, key=_score, reverse=True)

                msg_lines = [
                    f"doc totals mismatch (paid): sum(months)={sum_pd} vs 'ИТОГО ПО ПЕРИОДУ'={doc_total_paid} (delta={delta})",
                ]

                # Extra pinpoint: month(s) whose paid_total matches |delta| exactly (common failure mode)
                suspects = [
                    m
                    for (m, _ch, pd, _db, _pd_rows) in rows
                    if _close(pd, delta.copy_abs())
                ]
                if suspects:
                    msg_lines.append(
                        f"Suspect month(s) where paid_total≈|delta|: {', '.join(suspects)}"
                    )

                # Also highlight months with no dated payments but non-zero paid_total
                no_rows_nonzero_paid = [
                    m
                    for (m, _ch, pd, _db, pd_rows) in rows
                    if _close(pd_rows, Decimal("0.00"))
                    and not _close(pd, Decimal("0.00"))
                ]
                if no_rows_nonzero_paid:
                    msg_lines.append(
                        f"Months with paid_rows=0 but paid_total>0: {', '.join(no_rows_nonzero_paid[:12])}"
                    )

                msg_lines.append("Top months by inconsistency:")

                for m, ch, pd, db, pd_rows in rows_sorted[:12]:
                    implied_db = (ch - pd).quantize(TOL)
                    msg_lines.append(
                        f"  {m}: charged={ch} paid_total={pd} debt_total={db} paid_rows={pd_rows} (charged-paid_total={implied_db})"
                    )

                raise UserFacingError(
                    code="DOC_TOTALS_MISMATCH_PAID",
                    stage="pdf_to_json",
                    message=(
                        "Ошибка проверки справки: не сошлись итоги по оплатам. "
                        "Сумма оплат по периодам не равна значению в строке «ИТОГО ПО ПЕРИОДУ»."
                    ),
                    details={
                        "sum_periods_paid": str(sum_pd),
                        "doc_total_paid": str(doc_total_paid),
                        "delta": str(delta),
                        # важно: сохраняем твою диагностику (top suspects) в details, чтобы при желании
                        # показывать в UI по кнопке "Подробнее", либо хотя бы иметь в логах/статусе.
                        "diagnostics": msg_lines[
                            :80
                        ],  # ограничим размер, чтобы не раздувать JSON
                    },
                )

        if not _close(sum_db, doc_total_debt):
            raise UserFacingError(
                code="DOC_TOTALS_MISMATCH_DEBT",
                stage="pdf_to_json",
                message=(
                    "Ошибка проверки справки: не сошлись итоги по задолженности. "
                    "Сумма задолженности по периодам не равна значению в строке «ИТОГО ПО ПЕРИОДУ»."
                ),
                details={
                    "sum_periods_debt": str(sum_db),
                    "doc_total_debt": str(doc_total_debt),
                },
            )

        # ---------------------------
    # Normalize ordinary payments by period (domain rules)
    # ---------------------------

    def _normalize_and_validate_payments() -> None:
        """
        Domain rules:
          - ordinary payments must never be 0.00 -> treat as noise and drop
          - if both +X and -X exist for same date, they cancel out -> drop both
          - after normalization, sum(payments for period) MUST match printed paid_total for that period
        """
        # Collect ordinary payments indices by period
        by_period: Dict[str, List[Tuple[int, str, Decimal]]] = {}
        for idx, p in enumerate(payments):
            if p.get("kind") == "annual_adjustment_share":
                continue
            per = p.get("period")
            dt = p.get("date")
            if not per or not dt:
                continue
            try:
                amt = Decimal(
                    str(p.get("amount")).replace(" ", "").replace(",", ".")
                ).quantize(TOL)
            except Exception:
                continue
            by_period.setdefault(per, []).append((idx, dt, amt))

        to_remove: set[int] = set()

        # 1) Drop zero-amount payments (noise)
        for per, rows in by_period.items():
            for idx, _dt, amt in rows:
                if _close(amt, Decimal("0.00")):
                    to_remove.add(idx)

        # 2) Cancel opposite-sign pairs with same date and abs(amount)
        for per, rows in by_period.items():
            buckets: Dict[Tuple[str, Decimal], Dict[str, List[int]]] = {}
            for idx, dt, amt in rows:
                if idx in to_remove:
                    continue
                key = (dt, amt.copy_abs())
                b = buckets.setdefault(key, {"pos": [], "neg": []})
                if amt >= Decimal("0.00"):
                    b["pos"].append(idx)
                else:
                    b["neg"].append(idx)

            for (dt, abs_amt), b in buckets.items():
                k = min(len(b["pos"]), len(b["neg"]))
                if k <= 0:
                    continue
                # Deterministic cancellation: remove first k in insertion order
                for j in range(k):
                    to_remove.add(b["pos"][j])
                    to_remove.add(b["neg"][j])

        if to_remove:
            payments[:] = [p for i, p in enumerate(payments) if i not in to_remove]

        # 3) Strict per-period validation: sum(normalized payment rows) == month_total_paid[period]
        # Recompute sums from normalized payments
        sum_rows: Dict[str, Decimal] = {}
        for p in payments:
            if p.get("kind") == "annual_adjustment_share":
                continue
            per = p.get("period")
            if not per:
                continue
            try:
                amt = Decimal(
                    str(p.get("amount")).replace(" ", "").replace(",", ".")
                ).quantize(TOL)
            except Exception:
                continue
            sum_rows[per] = (sum_rows.get(per, Decimal("0.00")) + amt).quantize(TOL)

        # Validate for every parsed month period we finalized
        for per, paid_total in month_total_paid.items():
            paid_total = paid_total.quantize(TOL)
            s = sum_rows.get(per, Decimal("0.00")).quantize(TOL)
            if not _close(s, paid_total):
                delta = (s - paid_total).quantize(TOL)

                # Build small diagnostics: show all normalized payments for that period
                rows_dbg: List[str] = []
                for p in payments:
                    if p.get("kind") == "annual_adjustment_share":
                        continue
                    if p.get("period") != per:
                        continue
                    rows_dbg.append(f"{p.get('date')} {p.get('amount')}")

                raise UserFacingError(
                    code="PAYMENTS_PERIOD_SUM_MISMATCH",
                    stage="pdf_to_json",
                    message=(
                        f"Ошибка проверки справки: не сходятся оплаты за период {per}. "
                        "Сумма платежей по строкам не равна итогу оплаты за период в справке."
                    ),
                    details={
                        "period": per,
                        "sum_payment_rows": str(s),
                        "paid_total_printed": str(paid_total),
                        "delta": str(delta),
                        "payments_rows": rows_dbg[:40],
                    },
                )

    _normalize_and_validate_payments()

    return charges, payments
