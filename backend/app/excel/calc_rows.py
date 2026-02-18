from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from ..contracts.statement import Statement
from .penalty_rules import split_by_fraction_boundaries, normalize_category


@dataclass(frozen=True)
class CalcParams:
    category: str
    overdue_start_day: int   # день месяца (1..31), выбранный пользователем
    calc_date: date          # дата окончания расчёта (B10)


@dataclass
class CalcRow:
    # A–M
    period_label: str = ""                # A
    note: str = ""                        # B
    charged: Optional[Decimal] = None     # C
    paid: Optional[Decimal] = None        # D
    pay_date: Optional[date] = None       # E
    debt_formula: Optional[str] = None    # F (рендерер)
    overdue_from: Optional[date] = None   # G
    overdue_to: Optional[date] = None     # H
    days_formula: Optional[str] = None    # I (рендерер)
    key_rate: Optional[Decimal] = None    # J
    fraction: Optional[Decimal] = None    # K
    formula_text: str = ""                # L
    penalty_formula: Optional[str] = None # M (рендерер)

    # служебное
    _base_overdue_start: Optional[date] = None


def build_calc_rows(stmt: Statement) -> Tuple[List[CalcRow], CalcParams]:
    body = stmt.statement

    def _is_zero_money(v: Decimal) -> bool:
        # exact cents
        return v.quantize(Decimal("0.01")) == Decimal("0.00")
    
    def is_aa(obj: Any) -> bool:
        return (getattr(obj, "kind", None) or "") == "annual_adjustment_share"

    def _payment_date(p: Any) -> date:
        """Accessor for Payment.date (DD.MM.YYYY) as datetime.date."""
        return _parse_date(getattr(p, "date"))

    def _payment_period(p: Any) -> Optional[str]:
        """Accessor for Payment.period (MM.YYYY) for ordinary payments."""
        return getattr(p, "period", None)

    raw_category = body.category or _infer_category_from_debtor_name(getattr(body.debtor, "name", "") or "")
    category = normalize_category(raw_category)
    overdue_start_day = int(getattr(body, "overdue_start_day", None) or 1)
    calc_date = _parse_date(body.calc_date)

    params = CalcParams(
        category=category,
        overdue_start_day=overdue_start_day,
        calc_date=calc_date,
    )

    # ----------------------------
    # 1) Charges
    # ----------------------------
    month_charges: Dict[str, Decimal] = {}
    aa_charges: Dict[Tuple[str, str, str], Decimal] = {}  # (payable_month, adjustment_year, base_period) -> amount

    for ch in body.charges:
        amt = _dec_money(ch.amount)
        if is_aa(ch):
            key = (
                getattr(ch, "payable_month", "") or "",
                str(getattr(ch, "adjustment_year", "") or ""),
                getattr(ch, "base_period", None) or "",
            )
            aa_charges[key] = aa_charges.get(key, Decimal("0.00")) + amt
        else:
            per = ch.period
            month_charges[per] = month_charges.get(per, Decimal("0.00")) + amt

    month_periods = sorted(month_charges.keys(), key=_month_period_sort_key)

    # ----------------------------
    # 2) Payments
    # ----------------------------
    payments_by_period: Dict[str, List[Tuple[date, Decimal]]] = {p: [] for p in month_periods}
    aa_payments: Dict[Tuple[str, str, str], List[Tuple[date, Decimal]]] = {}

    for p in body.payments:
        d = _payment_date(p)
        amt = _dec_money(p.amount)

        if is_aa(p):
            key = (
                getattr(p, "payable_month", "") or "",
                str(getattr(p, "adjustment_year", "") or ""),
                getattr(p, "base_period", None) or "",
            )
            aa_payments.setdefault(key, []).append((d, amt))
        else:
            if not _payment_period(p):
                raise ValueError("payment.period is required (MM.YYYY)")
            per = _payment_period(p)
            if per in payments_by_period:
                payments_by_period[per].append((d, amt))

    for per in payments_by_period:
        payments_by_period[per].sort(key=lambda x: x[0])
    for key in aa_payments:
        aa_payments[key].sort(key=lambda x: x[0])
        
    # Optional exclusion of zero-debt periods / AA shares
    if bool(getattr(body, "exclude_zero_debt_periods", False)):
        kept_periods: List[str] = []
        for per in month_periods:
            charged = month_charges.get(per, Decimal("0.00"))
            paid = sum((amt for _d, amt in payments_by_period.get(per, [])), Decimal("0.00"))
            debt = charged - paid
            if not _is_zero_money(debt):
                kept_periods.append(per)

        month_periods = kept_periods
        payments_by_period = {p: payments_by_period.get(p, []) for p in month_periods}

        kept_aa_charges: Dict[Tuple[str, str, str], Decimal] = {}
        kept_aa_payments: Dict[Tuple[str, str, str], List[Tuple[date, Decimal]]] = {}
        for key, charged in aa_charges.items():
            paid = sum((amt for _d, amt in aa_payments.get(key, [])), Decimal("0.00"))
            debt = charged - paid
            if not _is_zero_money(debt):
                kept_aa_charges[key] = charged
                if key in aa_payments:
                    kept_aa_payments[key] = aa_payments[key]
        aa_charges = kept_aa_charges
        aa_payments = kept_aa_payments

    # ----------------------------
    # 3) Helpers
    # ----------------------------

    AA_LABEL_TMPL = (
        "Доля от размера годовой корректировки платы за тепловую энергию "
        "по итогам {year} года, подлежащая оплате в {payable_text}"
    )

    def _payable_text_from_period(period_mm_yyyy: str) -> str:
        """
        Требование ТЗ: в A-колонке AA-блока должно быть "... подлежащая оплате в январе 2025".
        То есть месяц — в ПРЕДЛОЖНОМ падеже (в январе, в феврале, ...).
        """
        mm, yyyy = period_mm_yyyy.split(".")
        months_prep = {
            "01": "январе", "02": "феврале", "03": "марте", "04": "апреле",
            "05": "мае", "06": "июне", "07": "июле", "08": "августе",
            "09": "сентябре", "10": "октябре", "11": "ноябре", "12": "декабре",
        }
        return f"{months_prep.get(mm, mm)} {yyyy}"

    def make_segments(
        *,
        start: date,
        end: date,
        overdue_start: date,
        category: str,
    ) -> List[Tuple[date, date, Decimal]]:
        """
        Returns list of segments (from, to, fraction).
        Adds zero-fraction segment before overdue_start automatically.
        """
        if end < start:
            return []
        zero = Decimal("0")
        if end < overdue_start:
            return [(start, end, zero)]
        if start < overdue_start <= end:
            out = [(start, overdue_start - timedelta(days=1), zero)]
            out.extend(
                split_by_fraction_boundaries(
                    category=category,
                    start=overdue_start,
                    end=end,
                    base_overdue_start=overdue_start,
                )
            )
            return out
        return split_by_fraction_boundaries(
            category=category,
            start=start,
            end=end,
            base_overdue_start=overdue_start,
        )

    def interval_end(event_dates: List[date], i: int) -> date:
        """
        Эталонное правило: если следующее событие в тот же день,
        интервал всё равно 1-дневный (start=end=event_date).
        """
        if i + 1 < len(event_dates):
            return max(event_dates[i], event_dates[i + 1] - timedelta(days=1))
        return calc_date

    def attach_segments_to_event_row(
        event_row: CalcRow,
        segs: List[Tuple[date, date, Decimal]],
        *,
        overdue_start: date,
    ) -> List[CalcRow]:
        """
        Первую часть сегмента кладём В ТУ ЖЕ строку события (как в эталоне),
        остальные сегменты — отдельными тех-строками.
        """
        if not segs:
            return [event_row]

        out_rows: List[CalcRow] = []
        s0, e0, f0 = segs[0]
        out_rows.append(_clone_with_interval(event_row, s0, e0, f0, overdue_start))

        for s, e, f in segs[1:]:
            out_rows.append(_clone_with_interval(CalcRow(), s, e, f, overdue_start))

        return out_rows

    def drop_leading_zero_segment_for_charge_row(
        segs: List[Tuple[date, date, Decimal]],
        *,
        overdue_start: date,
        charge_row: CalcRow,
    ) -> List[Tuple[date, date, Decimal]]:
        """
        UX requirement:
          Do not emit the initial "informational" zero-fraction interval
          that spans from debt_start (last day of month) to the day before
          overdue_start when there are no payments on that first row.

        Keep zero-fraction segments ONLY when they correspond to a payment row
        (i.e. the row has pay_date).
        """
        if not segs:
            return segs

        # If the charge row itself contains a payment (payment-on-debt_start),
        # keep the leading segment: user explicitly wants to see payments before overdue.
        if charge_row.pay_date is not None:
            return segs

        out = list(segs)
        zero = Decimal("0")
        while out and out[0][2] == zero and out[0][1] < overdue_start:
            out.pop(0)
        return out

    # ----------------------------
    # 4) Build rows month-by-month
    # ----------------------------
    rows: List[CalcRow] = []

    for period in month_periods:
        debt_start = _debt_start_for_period(period)
        overdue_start = _overdue_start_for_period(period, overdue_start_day)

        # ----------------------------
        # Base month block (ordinary)
        # ----------------------------

        # Charge row
        charge_row = CalcRow(
            period_label=_period_label(period),
            note="-",
            charged=month_charges[period],
        )

        pays = list(payments_by_period.get(period, []))
        if pays and pays[0][0] == debt_start:
            pay_on_debt_start = pays.pop(0)
            charge_row.paid = pay_on_debt_start[1]
            charge_row.pay_date = pay_on_debt_start[0]

        event_dates: List[date] = [debt_start] + [d for d, _ in pays]

        segs0 = make_segments(
            start=debt_start,
            end=interval_end(event_dates, 0),
            overdue_start=overdue_start,
            category=category,
        )

        segs0 = drop_leading_zero_segment_for_charge_row(
            segs0,
            overdue_start=overdue_start,
            charge_row=charge_row,
        )
        rows.extend(attach_segments_to_event_row(charge_row, segs0, overdue_start=overdue_start))

        for idx, (pay_dt, pay_amt) in enumerate(pays, start=1):
            pay_row = CalcRow(paid=pay_amt, pay_date=pay_dt)
            segs = make_segments(
                start=pay_dt,
                end=interval_end(event_dates, idx),
                overdue_start=overdue_start,
                category=category,
            )
            rows.extend(attach_segments_to_event_row(pay_row, segs, overdue_start=overdue_start))

        # ----------------------------
        # 5) Annual adjustment share blocks (AA)
        # Rule: insert AA block AFTER the base month block of payable_month.
        # Block header (column A) must be the full AA text from TЗ.
        # ----------------------------

        aa_keys_for_month = [k for k in aa_charges.keys() if k[0] == period]
        aa_keys_for_month.sort(key=lambda k: (k[1], k[2]))  # (adjustment_year, base_period)

        for key in aa_keys_for_month:
            payable_month, adj_year_str, base_period = key
            aa_amt = aa_charges[key]

            # Column A text must be the full phrase (as in TЗ)
            aa_label = AA_LABEL_TMPL.format(
                year=adj_year_str,
                payable_text=_payable_text_from_period(payable_month),
            )

            # AA charge row starts a NEW block in renderer (period_label + charged != None)
            aa_block_row = CalcRow(
                period_label=aa_label,
                note="-",
                charged=aa_amt,
            )

            aa_pays = list(aa_payments.get(key, []))

            # AA uses the same debt_start/overdue_start of the PAYABLE month block
            aa_debt_start = debt_start

            if aa_pays and aa_pays[0][0] == aa_debt_start:
                pay_on_debt_start = aa_pays.pop(0)
                aa_block_row.paid = pay_on_debt_start[1]
                aa_block_row.pay_date = pay_on_debt_start[0]

            aa_event_dates: List[date] = [aa_debt_start] + [d for d, _ in aa_pays]

            segs0 = make_segments(
                start=aa_debt_start,
                end=interval_end(aa_event_dates, 0),
                overdue_start=overdue_start,
                category=category,
            )
            segs0 = drop_leading_zero_segment_for_charge_row(
                segs0,
                overdue_start=overdue_start,
                charge_row=aa_block_row,
            )
            rows.extend(attach_segments_to_event_row(aa_block_row, segs0, overdue_start=overdue_start))

            for idx, (pay_dt, pay_amt) in enumerate(aa_pays, start=1):
                pay_row = CalcRow(paid=pay_amt, pay_date=pay_dt)
                segs = make_segments(
                    start=pay_dt,
                    end=interval_end(aa_event_dates, idx),
                    overdue_start=overdue_start,
                    category=category,
                )
                rows.extend(attach_segments_to_event_row(pay_row, segs, overdue_start=overdue_start))

    return rows, params


def _clone_with_interval(row: CalcRow, start: date, end: date, frac: Decimal, base_overdue_start: date) -> CalcRow:
    return CalcRow(
        period_label=row.period_label,
        note=row.note,
        charged=row.charged,
        paid=row.paid,
        pay_date=row.pay_date,
        overdue_from=start,
        overdue_to=end,
        fraction=frac,
        _base_overdue_start=base_overdue_start,
    )


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%d.%m.%Y").date()


def _dec_money(s: str) -> Decimal:
    return Decimal(s).quantize(Decimal("0.01"))


def _month_period_sort_key(period_mm_yyyy: str) -> date:
    mm, yyyy = period_mm_yyyy.split(".")
    return date(int(yyyy), int(mm), 1)


def _debt_start_for_period(period_mm_yyyy: str) -> date:
    mm, yyyy = period_mm_yyyy.split(".")
    return _last_day_of_month(int(yyyy), int(mm))


def _overdue_start_for_period(period_mm_yyyy: str, overdue_start_day: int) -> date:
    mm, yyyy = period_mm_yyyy.split(".")
    mm, yyyy = int(mm), int(yyyy)
    if mm == 12:
        mm, yyyy = 1, yyyy + 1
    else:
        mm += 1
    last = _last_day_of_month(yyyy, mm)
    return date(yyyy, mm, min(overdue_start_day, last.day))


def _last_day_of_month(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def _period_label(period_mm_yyyy: str) -> str:
    mm, yyyy = period_mm_yyyy.split(".")
    months = {
        "01": "Январь", "02": "Февраль", "03": "Март", "04": "Апрель",
        "05": "Май", "06": "Июнь", "07": "Июль", "08": "Август",
        "09": "Сентябрь", "10": "Октябрь", "11": "Ноябрь", "12": "Декабрь",
    }
    return f"{months.get(mm, mm)} {yyyy}"


def _infer_category_from_debtor_name(name: str) -> str:
    n = (name or "").lower()
    if "управляющ" in n or "ук" in n:
        return "Управляющая организация"
    if "тсж" in n or "жск" in n or "жилищный кооператив" in n:
        return "ТСЖ, ЖСК, ЖК"
    return "Прочие"
