from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ...normalize.dates import last_day_of_month
from ..errors import ParseError
from .statement_meta import parse_meta
from .statement_header import parse_header
from .statement_tables import parse_tables

_DOC_HDR_RE = re.compile(r"^Справка\s+о\s+задолженности", re.IGNORECASE)
_CONTRACT_NO_RE = re.compile(r"^[0-9А-ЯA-Z][0-9А-ЯA-Z\.\-\/]*$", re.IGNORECASE)

_CONSUMER_RE = re.compile(
    r"^Потребитель\s*(?:ТЭ|ГВС)?\s*:\s*(.+)\s*$",
    re.IGNORECASE,
)

def _extract_consumer_name_from_header(lines: List[str], start_from: int = 0) -> Optional[str]:
    """
    Fallback for debtor.name from header.

    Handles cases like:
      Потребитель ТЭ: <name>
      Потребитель ТЭ:
        <name>
    """
    i = start_from
    while i < len(lines):
        ln = (lines[i] or "").strip()
        if not ln:
            i += 1
            continue

        # нашли строку с "Потребитель"
        if re.search(r"\bПотребитель\b", ln, re.IGNORECASE):
            # вариант 1: имя в той же строке после двоеточия
            m = re.search(r":\s*(.+)$", ln)
            if m:
                name = m.group(1).strip()
                if HAS_LETTER_RE.search(name):
                    return name

            # вариант 2: имя в следующей строке
            j = i + 1
            while j < len(lines):
                nxt = (lines[j] or "").strip()
                if nxt:
                    if HAS_LETTER_RE.search(nxt):
                        return nxt
                    break
                j += 1

        i += 1

    return None


_STOP_NAME_MARKERS = (
    "Оплата",  # в реальных справках это заголовок столбца
    "ИТОГО ПО ПЕРИОДУ",
    "Выставленный счет",
)

# Строки нижних таблиц часто начинаются так: "1 10.12.2025 ..." (№ строки + дата)
_ROWNO_DATE_RE = re.compile(r"^\d+\s+\d{2}\.\d{2}\.\d{4}\b")
# Внутри строки имени иногда прилипает хвост " 1 10.12.2025" — отрежем всё с первого такого паттерна
_CUT_AFTER_ROWNO_DATE_RE = re.compile(r"\s+\d+\s+\d{2}\.\d{2}\.\d{4}\b")
# Иногда прилипает " 10.12.2025 14:04"
_CUT_AFTER_DATE_TIME_RE = re.compile(r"\s+\d{2}\.\d{2}\.\d{4}\s+\d{1,2}:\d{2}\b")

# --- OPF canonicalization: PDF may contain abbreviations at the beginning (ООО/АО/ПАО/ГУП/МУП/...)
# We must output debtor.name starting with FULL canonical OPF.
_OPF_ABBR_TO_FULL: Dict[str, str] = {
    "ООО": "Общество с ограниченной ответственностью",
    "АО": "Акционерное общество",
    "ПАО": "Публичное акционерное общество",
    "ГУП": "Государственное унитарное предприятие",
    "МУП": "Муниципальное унитарное предприятие",
    "НКО": "Некоммерческая организация",
    "АНО": "Автономная некоммерческая организация",
    # Частые учреждения (если в PDF встречаются как аббревиатуры)
    "ГБУ": "Государственное бюджетное учреждение",
    "ГАУ": "Государственное автономное учреждение",
    "МБУ": "Муниципальное бюджетное учреждение",
    "МАУ": "Муниципальное автономное учреждение",
    "ФГБУ": "Федеральное государственное бюджетное учреждение",
    "ФГАУ": "Федеральное государственное автономное учреждение",
}

_LEADING_JUNK_RE = re.compile(r'^[\s"«»„“”\(\)\[\]\{\}]+')

def _strip_leading_junk(s: str) -> str:
    return _LEADING_JUNK_RE.sub("", (s or "").strip())

def _canonicalize_opf_prefix(name: str) -> str:
    """
    If name starts with OPF abbreviation (ООО/АО/...), replace it with full canonical OPF.
    Keeps the rest of the name unchanged (except leading quotes/brackets are trimmed).
    """
    s = _strip_leading_junk(name)
    if not s:
        return s

    # Match first token (letters/digits, no spaces), typical for abbreviations.
    m = re.match(r"^([A-Za-zА-Яа-яЁё]+)\b(.*)$", s)
    if not m:
        return s

    head = m.group(1).replace("Ё", "Е").replace("ё", "е").upper()
    tail = m.group(2) or ""
    full = _OPF_ABBR_TO_FULL.get(head)
    if not full:
        return s

    # Avoid double spaces.
    tail = tail.lstrip()
    return f"{full} {tail}".strip()

_OPF_FULL = [
    "Общество с ограниченной ответственностью",
    "Акционерное общество",
    "Публичное акционерное общество",
    "Товарищество собственников жилья",
    "Жилищно-строительный кооператив",
    "Жилищный кооператив",
    "Государственное бюджетное учреждение",
    "Государственное автономное учреждение",
    "Муниципальное бюджетное учреждение",
    "Муниципальное автономное учреждение",
    "Федеральное государственное бюджетное учреждение",
    "Федеральное государственное автономное учреждение",
    "Государственное унитарное предприятие",
    "Муниципальное унитарное предприятие",
    "Некоммерческая организация",
    "Автономная некоммерческая организация",
    "Фонд",
    "Бюджетное учреждение",
    "Совет общественного самоуправления",
    "ДЕПАРТАМЕНТ",
    "КОМИТЕТ",
    "МИНИСТЕРСТВО",
    "УПРАВЛЕНИЕ",
    "ИНСПЕКЦИЯ",
    "АДМИНИСТРАЦИЯ",
    "ПРЕФЕКТУРА",
    "СЛУЖБА",
    "АГЕНТСТВО",
    "УФК",
    "ФКУ",
    "ФГБУ",
    "ФБУ",
    "ФКП",
    "ГБУ",
    "ГАУ",
    "ГАУЗ",
    "МБУ",
    "АУ",
    "БУ",
    "ТСЖ",
    "ЖСК",
    "ЖК",
    "СНТ",
]

HAS_LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")

def _norm_for_opf(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("Ё", "Е").replace("ё", "е")
    s = s.upper()
    s = re.sub(r"\s+", " ", s)
    return s


# --- OPF list comes from backend/app/data/opf.yml when available (fallback to hardcoded list above).
# This keeps quality-check OPF rules in sync without changing parser output semantics.
try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


def _load_opf_items_from_yml() -> Optional[List[str]]:
    if yaml is None:
        return None
    # .../app/extract/parsers/statement_parser.py -> .../app
    app_dir = Path(__file__).resolve().parents[2]
    yml_path = app_dir / "data" / "opf.yml"
    if not yml_path.exists():
        return None
    try:
        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        items = [x.strip() for x in data["items"] if isinstance(x, str) and x.strip()]
        return items or None
    return None


def _derive_opf_abbr_map(items: List[str]) -> Dict[str, str]:
    """Derive abbreviation -> full OPF mapping from items list.

    Rule: if an item is a short ALLCAPS token (e.g., ГБУ) and there exists a full-form item whose acronym matches it,
    then map abbr -> that full form (unless already in _OPF_ABBR_TO_FULL).
    """
    fulls = [x for x in items if (" " in x.strip() or "-" in x.strip() or "–" in x or "—" in x)]
    abbrs = [x.strip() for x in items if (" " not in x.strip())]

    def acronym(full: str) -> str:
        s = re.sub(r"[-–—]", " ", full)
        parts = [p for p in re.split(r"\s+", s.strip()) if p]
        letters = [p[0] for p in parts if re.search(r"[A-Za-zА-Яа-яЁё]", p)]
        return _norm_for_opf("".join(letters))

    ac_map: Dict[str, str] = {}
    for f in fulls:
        ac = acronym(f)
        if ac and ac not in ac_map:
            ac_map[ac] = f

    out: Dict[str, str] = {}
    for a in abbrs:
        a_norm = _norm_for_opf(a)
        if a_norm in _OPF_ABBR_TO_FULL:
            continue
        f = ac_map.get(a_norm)
        if f:
            out[a_norm] = f
    return out


_loaded_items = _load_opf_items_from_yml()
if _loaded_items:
    _OPF_FULL = _loaded_items
    for k_norm, full in _derive_opf_abbr_map(_loaded_items).items():
        _OPF_ABBR_TO_FULL[k_norm] = full


_OPF_FULL_NORM = [_norm_for_opf(x) for x in _OPF_FULL]

def parse_statement(
    lines: List[str],
    source_pdf: str,
    category: Optional[str] = None,
    *,
    calc_date_override: str,
    rate_percent: float,
    overdue_start_day: int,
) -> Dict:
    meta, period_from, _calc_date_from_pdf = parse_meta(lines, source_pdf)

    debtor, contract = parse_header(lines)

    charges, payments = parse_tables(lines)

    contract_no, debtor_name = _parse_bottom_block(lines)
    debtor["name"] = debtor_name
    contract["number"] = contract_no

    period_to = last_day_of_month(charges[-1]["period"])
    totals = _compute_totals(charges, payments)

    statement: Dict = {
        "debtor": debtor,
        "contract": contract,
        "period": {"from": period_from, "to": period_to},
        "calc_date": calc_date_override,
        "rate_percent": rate_percent,
        "overdue_start_day": overdue_start_day,
        "charges": charges,
        "payments": payments,
        "totals": totals,
    }
    if category is not None:
        statement["category"] = category

    return {
        "schema_version": "1.2",
        "meta": meta,
        "statement": statement,
    }


def _parse_bottom_block(lines: List[str]) -> Tuple[str, str]:
    """
    Достаём:
      contract.number
      debtor.name

    ВАЖНО: наименование должника всегда начинается с полной ОПФ
    (или с аббревиатуры, которая приводится к полной форме).

    В текущем проекте часть должников (учреждения) в PDF может начинаться
    с "Государственное бюджетное общеобразовательное учреждение ...",
    "Федеральное казенное учреждение ...", и т.п. — это тоже считаем OPF-start.
    """
    start_idx = None
    for i, ln in enumerate(lines):
        if _DOC_HDR_RE.match(ln):
            start_idx = i
            break
    if start_idx is None:
        raise ParseError("document header 'Справка о задолженности' not found")

    # ----------------------------
    # contract.number (FIXED)
    # ----------------------------
    # ВАЖНОЕ ПРАВИЛО: номер договора должен начинаться с цифры.
    # Допустимы:
    #   01.000178 ТЭ
    #   01.000178ТЭ
    #   09.346737кГВ
    #   44039
    #
    # Нельзя:
    #   "Оплата"
    #   "СЗ ..."
    #   табличные строки вида "1 10.12.2025 ..."
    #   дроби "1/12", "1/300" и т.п.
    _CONTRACT_CANDIDATE_RE = re.compile(
        r"^\d[0-9A-Za-zА-Яа-яЁё\.\-\/]*"
        r"(?:\s+[0-9A-Za-zА-Яа-яЁё][0-9A-Za-zА-Яа-яЁё\.\-\/]*)?$"
    )
    _FRACTION_RE = re.compile(r"^\d+\s*/\s*\d+$")

    def _norm_contract_line(s: str) -> str:
        s = (s or "").strip()
        s = re.sub(r"\s+", " ", s)
        return s

    def _is_contract_line(s: str) -> bool:
        s = _norm_contract_line(s)
        if not s:
            return False

        low = s.lower()

        # стоп-слова нижнего блока
        if low in {"оплата", "выставленный счет", "итого по периоду"}:
            return False

        # "СЗ ..." не может быть номером договора
        if low.startswith("сз"):
            return False

        # табличная часть
        if _ROWNO_DATE_RE.match(s):
            return False

        # исключаем дроби типа 1/12, 1/300, 1/130 и т.п.
        if _FRACTION_RE.match(s):
            return False

        # must start with digit (guaranteed by regex, but keep explicit)
        if not re.match(r"^\d", s):
            return False

        # основной паттерн (разрешает один пробел между номером и суффиксом)
        if not _CONTRACT_CANDIDATE_RE.match(s):
            return False

        # должен содержать хотя бы одну цифру (защита от странных артефактов)
        if not re.search(r"\d", s):
            return False

        return True

    contract_no = None

    # 1) Сначала ищем в небольшом окне после заголовка (это безопаснее и не цепляет "Оплата")
    scan_hi = min(len(lines), start_idx + 80)
    idx = start_idx + 1
    while idx < scan_hi:
        ln = _norm_contract_line(lines[idx])
        if _is_contract_line(ln):
            contract_no = ln
            idx += 1
            break
        idx += 1

    # 2) Fallback: если в окне не нашли (редкие кейсы), ищем дальше, но всё равно только digit-start
    if not contract_no:
        idx = start_idx + 1
        while idx < len(lines):
            ln = _norm_contract_line(lines[idx])
            if _is_contract_line(ln):
                contract_no = ln
                idx += 1
                break
            idx += 1

    if not contract_no:
        raise ParseError("contract.number not found after doc header")

    # --- local helpers (only inside this function to avoid side-effects) ---

    # Типовые "полные" формы учреждений/органов, которые часто идут в PDF
    # и не обязаны быть 1-в-1 в opf.yml items как "полные ОПФ".
    _INSTITUTION_OPF_RE = re.compile(
        r"^(ФЕДЕРАЛЬНОЕ|ГОСУДАРСТВЕННОЕ|МУНИЦИПАЛЬНОЕ)\s+"
        r"(КАЗЕННОЕ|КАЗЁННОЕ|БЮДЖЕТНОЕ|АВТОНОМНОЕ)\s+"
        r"(ОБЩЕОБРАЗОВАТЕЛЬНОЕ\s+)?УЧРЕЖДЕНИЕ\b",
        re.IGNORECASE,
    )

    def _collapse_abbr_glitches(s: str) -> str:
        """
        Fix typical text-layer glitches at the beginning:
          - 'Г Б У ...'  -> 'ГБУ ...'
          - 'Г.Б.У.'     -> 'ГБУ'
          - 'Ф.К.У ...'  -> 'ФКУ ...'
        """
        s0 = _strip_leading_junk(s or "")

        # spaced letters: "Г Б У ..." / "О О О ..."
        m_sp = re.match(r"^((?:[A-ZА-ЯЁ]\s+){2,}[A-ZА-ЯЁ])(\b.*)?$", s0)
        if m_sp:
            abbr = re.sub(r"\s+", "", m_sp.group(1))
            tail = (m_sp.group(2) or "")
            s0 = f"{abbr}{tail}"

        # dotted letters: "Г.Б.У." / "Ф.К.У"
        m_dot = re.match(r"^((?:[A-ZА-ЯЁ]\.){2,}[A-ZА-ЯЁ]\.?)\b(.*)$", s0)
        if m_dot:
            abbr = m_dot.group(1).replace(".", "")
            tail = (m_dot.group(2) or "")
            s0 = f"{abbr}{tail}"

        return s0

    def _is_opf_start(line: str) -> bool:
        """
        OPF-start if:
        1) starts with known full OPF from _OPF_FULL_NORM
        2) starts with known abbreviation from _OPF_ABBR_TO_FULL
        3) starts with common institution full form (Федеральное/Государственное/Муниципальное ... учреждение)
        4) starts with truncated 'Общество с ограниченной ответстве...' (text-layer glitch)
        """
        ln0 = _collapse_abbr_glitches(line)

        # ВАЖНО: нормализуем дефисы ДО opf-start проверки
        # (чинит "Жилищно - строительный ..." => "Жилищно-строительный ...")
        ln0 = re.sub(r"\s*-\s*", "-", ln0)

        ln0 = _CUT_AFTER_ROWNO_DATE_RE.split(ln0, maxsplit=1)[0]
        ln0 = _CUT_AFTER_DATE_TIME_RE.split(ln0, maxsplit=1)[0].strip()
        if not ln0:
            return False

        # 4) text-layer truncation for ООО
        # (чинит "Общество с ограниченной ответстве" => считаем OPF-start)
        if re.match(r"^Общество\s+с\s+ограниченной\s+ответств", ln0, flags=re.IGNORECASE):
            return True

        ln_norm = _norm_for_opf(ln0)

        # 1) full OPF items
        if any(ln_norm.startswith(opf) for opf in _OPF_FULL_NORM):
            return True

        # 2) abbreviation token
        first_token = ln_norm.split(" ", 1)[0] if ln_norm else ""
        if first_token in _OPF_ABBR_TO_FULL:
            return True

        # 3) учреждение в полной форме
        if _INSTITUTION_OPF_RE.match(ln0):
            return True

        return False

    # --- debtor.name: ищем по всей странице 1 (а не только в нижнем блоке) ---
    # Практически: в текстовом слое это первые ~300 строк после заголовка "Справка о задолженности".
    start_name_idx = None
    scan_limit = min(len(lines), start_idx + 300)
    j = start_idx + 1
    while j < scan_limit:
        ln = lines[j].strip()
        if not ln:
            j += 1
            continue

        # явные “служебные” штуки: если встретили до имени — продолжаем поиск
        if ln.startswith("ККС ") or ln.startswith("Дата с:") or "ИНН" in ln:
            j += 1
            continue

        # Табличная часть (№ строки + дата) — это точно не имя
        if _ROWNO_DATE_RE.match(ln):
            j += 1
            continue

        if _is_opf_start(ln):
            start_name_idx = j
            break

        j += 1

    if start_name_idx is None:
        # Fallback: debtor name may be in header line "Потребитель ...: ..."
        fallback = _extract_consumer_name_from_header(lines, start_from=start_idx)
        if fallback and HAS_LETTER_RE.search(fallback):
            debtor_name = fallback.strip()
            debtor_name = re.sub(r"\s*-\s*", "-", debtor_name)
            debtor_name = re.sub(
                r"^Общество\s+с\s+ограниченной\s+ответств[^\s]*\b",
                "Общество с ограниченной ответственностью",
                debtor_name,
                flags=re.IGNORECASE,
            )
            debtor_name = _canonicalize_opf_prefix(debtor_name)
            return contract_no, debtor_name

        raise ParseError("debtor.name (OPF-start) not found after contract.number")

    # --- собираем имя, начиная с строки ОПФ/наименования учреждения ---
    name_parts: List[str] = []
    idx = start_name_idx
    while idx < len(lines):
        ln = lines[idx].strip()
        if not ln:
            idx += 1
            continue

        if any(ln.startswith(m) for m in _STOP_NAME_MARKERS):
            break
        if ln.startswith("ККС ") or ln.startswith("Дата с:") or "ИНН" in ln:
            break

        # Началась табличная часть (№ строки + дата) — имя закончилось
        if _ROWNO_DATE_RE.match(ln):
            break

        # Если "хвост" прилип в той же строке — отрезаем его
        ln = _CUT_AFTER_ROWNO_DATE_RE.split(ln, maxsplit=1)[0]
        ln = _CUT_AFTER_DATE_TIME_RE.split(ln, maxsplit=1)[0]
        ln = ln.strip()

        if not ln:
            break

        name_parts.append(ln)
        idx += 1

    if not name_parts:
        raise ParseError("debtor.name not found after OPF start")

    debtor_name = " ".join(name_parts).strip()

    # Нормализация: "Жилищно - строительный" -> "Жилищно-строительный"
    debtor_name = re.sub(r"\s*-\s*", "-", debtor_name)

    # Частая поломка/обрезка слова в ОПФ: "ответстве" -> "ответственностью" (только в начале в контексте ОПФ)
    debtor_name = re.sub(
        r"^Общество\s+с\s+ограниченной\s+ответств[^\s]*\b",
        "Общество с ограниченной ответственностью",
        debtor_name,
        flags=re.IGNORECASE,
    )

    # Если после имени остались цифры/даты — отрезаем всё с первого "служебного" паттерна
    debtor_name = re.split(
        r"\s+\d+\s+\d{2}\.\d{2}\.\d{4}\b", debtor_name, maxsplit=1
    )[0].strip()

    debtor_name = _canonicalize_opf_prefix(debtor_name)

    # --- П.3: если получилась строка без букв, пробуем fallback "Потребитель ...: ..." ---
    if not HAS_LETTER_RE.search(debtor_name):
        fallback = _extract_consumer_name_from_header(lines, start_from=start_idx)
        if fallback and HAS_LETTER_RE.search(fallback):
            debtor_name = fallback.strip()
            debtor_name = re.sub(r"\s*-\s*", "-", debtor_name)
            debtor_name = re.sub(
                r"^Общество\s+с\s+ограниченной\s+ответств[^\s]*\b",
                "Общество с ограниченной ответственностью",
                debtor_name,
                flags=re.IGNORECASE,
            )
            debtor_name = _canonicalize_opf_prefix(debtor_name)
            return contract_no, debtor_name

        raise ParseError("debtor.name contains no letters (likely table row picked instead of name)")

    return contract_no, debtor_name


def _compute_totals(charges: List[Dict], payments: List[Dict]) -> Dict:
    def d(x: str) -> Decimal:
        return Decimal(x)

    charged = sum((d(c["amount"]) for c in charges), start=Decimal("0.00"))
    paid = sum((d(p["amount"]) for p in payments), start=Decimal("0.00"))
    debt = charged - paid

    return {
        "charged": f"{charged:.2f}",
        "paid": f"{paid:.2f}",
        "debt": f"{debt:.2f}",
    }
