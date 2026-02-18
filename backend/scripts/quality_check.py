from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Optional dependency. If you don't want PyYAML, switch to JSON for opf list.
try:
    import yaml  # type: ignore
except Exception:
    yaml = None


MONEY_RE = re.compile(r"^-?\d+\.\d{2}$")
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
PERIOD_RE = re.compile(r"^\d{2}\.\d{4}$")
HAS_LETTER_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")

CONTRACT_TOKENS = [
    "ТЭ", "ТЕ",           # ТЭ иногда превращается в ТЕ (извлечение)
    "ГВС", "ГВ",          # бывает и без "С"
    "КТЭ", "КТЕ",         # кТЭ / кТЕ
    "КГВС", "КГВ",        # кГВС / кГВ
    "РМ", "ПТЭ", "ФОТЭ", "БДП",
    "ТГВ",                # встречается как суффикс
]



def norm_text(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("Ё", "Е").replace("ё", "е")
    s = s.upper()
    s = re.sub(r"\s+", " ", s)
    return s


def norm_name_for_opf_check(s: str) -> str:
    # Strip leading quotes/brackets often seen in names.
    s = (s or "").strip()
    s = re.sub(r'^[\s"«»„“”\(\)\[\]\{\}]+', "", s)
    return norm_text(s)


def load_opf_list(opf_path: Path) -> List[str]:
    if not opf_path.exists():
        raise FileNotFoundError(f"OPF file not found: {opf_path}")

    if opf_path.suffix.lower() in (".yml", ".yaml"):
        if yaml is None:
            raise RuntimeError(
                "PyYAML is not installed, but opf.yml is used. Install pyyaml or use opf.json."
            )
        data = yaml.safe_load(opf_path.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ValueError("opf.yml must contain key 'items' as list of strings")
        return [str(x) for x in items]

    if opf_path.suffix.lower() == ".json":
        data = json.loads(opf_path.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ValueError("opf.json must contain key 'items' as list of strings")
        return [str(x) for x in items]

    raise ValueError("OPF file must be .yml/.yaml or .json")


@dataclass
class Issue:
    level: str  # "ERROR" | "WARN"
    path: str   # JSON path, e.g. statement.debtor.inn
    code: str   # stable machine code
    message: str


def get(obj: Dict[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def is_digits_len(s: str, lens: Tuple[int, ...]) -> bool:
    return s.isdigit() and len(s) in lens


def is_valid_period(p: str) -> bool:
    if not PERIOD_RE.match(p or ""):
        return False
    mm = int(p[:2])
    return 1 <= mm <= 12


def is_int_like_year(v: Any) -> bool:
    # Accept int(2024) or str("2024")
    if isinstance(v, int):
        return 1900 <= v <= 2100
    if isinstance(v, str) and v.strip().isdigit():
        y = int(v.strip())
        return 1900 <= y <= 2100
    return False


def has_any_adjustment_fields(item: Dict[str, Any]) -> bool:
    aa_fields = ["adjustment_year", "payable_month", "base_period"]
    return any((k in item and item.get(k) is not None) for k in aa_fields)


def check_statement(doc: Dict[str, Any], opf_norm_list: List[str]) -> List[Issue]:
    if not isinstance(doc, dict):
        return [Issue("ERROR", "$", "DOC_INVALID", "Root JSON must be an object")]

    # Skip non-statement JSONs (batch_report.json, quality_report.json, etc.)
    if "statement" not in doc:
        return [Issue("WARN", "statement", "NOT_STATEMENT_JSON", "No 'statement' key: file skipped")]

    st = get(doc, "statement")
    if not isinstance(st, dict):
        return [Issue("ERROR", "statement", "STATEMENT_INVALID", "Missing or invalid 'statement' object")]

    issues: List[Issue] = []

    # category must be absent or null (not in PDF)
    if "category" in st and st.get("category") is not None:
        issues.append(Issue("ERROR", "statement.category", "CATEGORY_PRESENT", "category must be absent (not in PDF)"))

    # debtor.name
    debtor_name = get(doc, "statement.debtor.name")
    if not isinstance(debtor_name, str) or not debtor_name.strip():
        issues.append(Issue("ERROR", "statement.debtor.name", "DEBTOR_NAME_EMPTY", "debtor.name is empty or missing"))
    else:
        if not HAS_LETTER_RE.search(debtor_name):
            issues.append(Issue("ERROR", "statement.debtor.name", "DEBTOR_NAME_NO_LETTERS", "debtor.name must contain letters"))

        # By agreement: name ALWAYS starts with full OPF (case-insensitive).
        dn = norm_name_for_opf_check(debtor_name)
        if not any(dn.startswith(opf) for opf in opf_norm_list):
            issues.append(Issue(
                "ERROR",
                "statement.debtor.name",
                "DEBTOR_NAME_NO_OPF_PREFIX",
                "debtor.name must start with full OPF (canonical), but no OPF prefix found",
            ))

    # debtor.inn
    inn = get(doc, "statement.debtor.inn")
    if not isinstance(inn, str) or not inn.strip():
        issues.append(Issue("ERROR", "statement.debtor.inn", "INN_EMPTY", "INN is empty or missing"))
    else:
        if not is_digits_len(inn, (10, 12)):
            issues.append(Issue("ERROR", "statement.debtor.inn", "INN_INVALID", "INN must be digits only, length 10 or 12"))

    # contract.number
    cnum = get(doc, "statement.contract.number")
    if not isinstance(cnum, str) or not cnum.strip():
        issues.append(Issue("ERROR", "statement.contract.number", "CONTRACT_NUMBER_EMPTY", "contract.number is empty or missing"))
    else:
        # normalize for token detection:
        # - upper + spaces (norm_text)
        # - latin-to-cyrillic lookalikes (common in PDF text extraction)
        cnum_n = norm_text(cnum)

        lat2cyr = str.maketrans({
            "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "K": "К",
            "M": "М", "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
        })
        cnum_tok = cnum_n.translate(lat2cyr)

        has_token = any(tok in cnum_tok for tok in CONTRACT_TOKENS)
        is_numericish = bool(re.fullmatch(r"[0-9./\-]+", cnum.strip()))

        # By rule: contract.number must start with a digit.
        # If it doesn't, keep WARN (we don't error-out to avoid regressions).
        starts_with_digit = bool(re.match(r"^\d", cnum.strip()))

        if not starts_with_digit or not (has_token or is_numericish):
            issues.append(Issue(
                "WARN",
                "statement.contract.number",
                "CONTRACT_NUMBER_UNUSUAL",
                "contract.number has no typical tokens and is not purely numeric-like",
            ))


    # contract.date
    cdate = get(doc, "statement.contract.date")
    if not isinstance(cdate, str) or not DATE_RE.match(cdate):
        issues.append(Issue("ERROR", "statement.contract.date", "CONTRACT_DATE_INVALID", "contract.date must be DD.MM.YYYY"))

    # period
    p_from = get(doc, "statement.period.from")
    p_to = get(doc, "statement.period.to")
    if not isinstance(p_from, str) or not DATE_RE.match(p_from):
        issues.append(Issue("ERROR", "statement.period.from", "PERIOD_FROM_INVALID", "period.from must be DD.MM.YYYY"))
    if not isinstance(p_to, str) or not DATE_RE.match(p_to):
        issues.append(Issue("ERROR", "statement.period.to", "PERIOD_TO_INVALID", "period.to must be DD.MM.YYYY"))

    # calc_date
    calc_date = get(doc, "statement.calc_date")
    if not isinstance(calc_date, str) or not DATE_RE.match(calc_date):
        issues.append(Issue("ERROR", "statement.calc_date", "CALC_DATE_INVALID", "calc_date must be DD.MM.YYYY"))

    # charges must be non-empty
    charges = get(doc, "statement.charges")
    if not isinstance(charges, list) or len(charges) == 0:
        issues.append(Issue("ERROR", "statement.charges", "CHARGES_EMPTY", "charges must be non-empty; empty indicates parsing failure"))
    else:
        for i, ch in enumerate(charges):
            if not isinstance(ch, dict):
                issues.append(Issue("ERROR", f"statement.charges[{i}]", "CHARGE_INVALID", "charge item must be object"))
                continue

            period = ch.get("period")
            amount = ch.get("amount")

            if not isinstance(period, str) or not is_valid_period(period):
                issues.append(Issue("ERROR", f"statement.charges[{i}].period", "CHARGE_PERIOD_INVALID", "charge.period must be MM.YYYY (01-12)"))
            if not isinstance(amount, str) or not MONEY_RE.match(amount):
                issues.append(Issue("ERROR", f"statement.charges[{i}].amount", "CHARGE_AMOUNT_INVALID", "charge.amount must be money string 12345.67"))

            # annual adjustment coherence (optional)
            if has_any_adjustment_fields(ch) or ch.get("kind") == "annual_adjustment_share":
                if ch.get("kind") != "annual_adjustment_share":
                    issues.append(Issue("ERROR", f"statement.charges[{i}].kind", "AA_KIND_INVALID", "kind must be annual_adjustment_share when adjustment fields are present"))
                if not is_int_like_year(ch.get("adjustment_year")):
                    issues.append(Issue("ERROR", f"statement.charges[{i}].adjustment_year", "AA_YEAR_INVALID", "adjustment_year must be int or numeric string YYYY"))
                pm = ch.get("payable_month")
                bp = ch.get("base_period")
                if not isinstance(pm, str) or not is_valid_period(pm):
                    issues.append(Issue("ERROR", f"statement.charges[{i}].payable_month", "AA_PAYABLE_MONTH_INVALID", "payable_month must be MM.YYYY"))
                if not isinstance(bp, str) or not is_valid_period(bp):
                    issues.append(Issue("ERROR", f"statement.charges[{i}].base_period", "AA_BASE_PERIOD_INVALID", "base_period must be MM.YYYY"))

    # payments
    payments = get(doc, "statement.payments")
    if isinstance(payments, list):
        for i, pm in enumerate(payments):
            if not isinstance(pm, dict):
                issues.append(Issue("ERROR", f"statement.payments[{i}]", "PAYMENT_INVALID", "payment item must be object"))
                continue

            dt = pm.get("date")
            amt = pm.get("amount")

            if not isinstance(dt, str) or not DATE_RE.match(dt):
                issues.append(Issue("ERROR", f"statement.payments[{i}].date", "PAYMENT_DATE_INVALID", "payment.date must be DD.MM.YYYY"))
            if not isinstance(amt, str) or not MONEY_RE.match(amt):
                issues.append(Issue("ERROR", f"statement.payments[{i}].amount", "PAYMENT_AMOUNT_INVALID", "payment.amount must be money string 12345.67 (negative allowed)"))

            # annual adjustment coherence (optional)
            if has_any_adjustment_fields(pm) or pm.get("kind") == "annual_adjustment_share":
                if pm.get("kind") != "annual_adjustment_share":
                    issues.append(Issue("ERROR", f"statement.payments[{i}].kind", "AA_KIND_INVALID", "kind must be annual_adjustment_share when adjustment fields are present"))
                if not is_int_like_year(pm.get("adjustment_year")):
                    issues.append(Issue("ERROR", f"statement.payments[{i}].adjustment_year", "AA_YEAR_INVALID", "adjustment_year must be int or numeric string YYYY"))
                payable_month = pm.get("payable_month")
                base_period = pm.get("base_period")
                if not isinstance(payable_month, str) or not is_valid_period(payable_month):
                    issues.append(Issue("ERROR", f"statement.payments[{i}].payable_month", "AA_PAYABLE_MONTH_INVALID", "payable_month must be MM.YYYY"))
                if not isinstance(base_period, str) or not is_valid_period(base_period):
                    issues.append(Issue("ERROR", f"statement.payments[{i}].base_period", "AA_BASE_PERIOD_INVALID", "base_period must be MM.YYYY"))

    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description="Quality checks for Statement JSONs")
    ap.add_argument("--in-dir", required=True, help="Folder with JSON files (recursive)")
    ap.add_argument("--opf", default="data/opf.yml", help="Path to OPF dictionary (yml/json)")
    ap.add_argument("--out", default="quality_report.json", help="Output report JSON")
    ap.add_argument("--out-txt", default="quality_report.txt", help="Output human-readable report")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    opf_path = Path(args.opf)

    opf_list = load_opf_list(opf_path)
    opf_norm = [norm_text(x) for x in opf_list]

    files = sorted(in_dir.rglob("*.json"))
    report: Dict[str, Any] = {
        "meta": {
            "in_dir": str(in_dir),
            "opf": str(opf_path),
            "files_total": len(files),
        },
        "results": [],
        "summary": {
            "files_ok": 0,
            "files_skipped": 0,
            "files_with_errors": 0,
            "files_with_warnings_only": 0,
            "errors_total": 0,
            "warnings_total": 0,
            "top_error_codes": {},
            "top_warn_codes": {},
        },
    }

    top_err: Dict[str, int] = {}
    top_warn: Dict[str, int] = {}

    lines_txt: List[str] = []
    for fp in files:
        issues: List[Issue] = []
        try:
            doc = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            doc = {}
            issues = [Issue("ERROR", "$", "JSON_PARSE_ERROR", f"Failed to parse JSON: {e}")]

        if not issues:
            issues = check_statement(doc, opf_norm)

        # Skip non-statement jsons
        if len(issues) == 1 and issues[0].code == "NOT_STATEMENT_JSON":
            report["summary"]["files_skipped"] += 1
            report["results"].append({"file": str(fp), "issues": [asdict(issues[0])]})
            continue

        err = [x for x in issues if x.level == "ERROR"]
        warn = [x for x in issues if x.level == "WARN"]

        for x in err:
            top_err[x.code] = top_err.get(x.code, 0) + 1
        for x in warn:
            top_warn[x.code] = top_warn.get(x.code, 0) + 1

        if not issues:
            report["summary"]["files_ok"] += 1
        else:
            if err:
                report["summary"]["files_with_errors"] += 1
            elif warn:
                report["summary"]["files_with_warnings_only"] += 1

        report["summary"]["errors_total"] += len(err)
        report["summary"]["warnings_total"] += len(warn)

        report["results"].append({
            "file": str(fp),
            "issues": [asdict(x) for x in issues],
        })

        if issues:
            lines_txt.append(f"\n=== {fp} ===")
            for x in issues:
                lines_txt.append(f"{x.level} {x.code} {x.path}: {x.message}")

    report["summary"]["top_error_codes"] = dict(sorted(top_err.items(), key=lambda kv: kv[1], reverse=True))
    report["summary"]["top_warn_codes"] = dict(sorted(top_warn.items(), key=lambda kv: kv[1], reverse=True))

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out_txt).write_text("\n".join(lines_txt).lstrip() + ("\n" if lines_txt else ""), encoding="utf-8")

    print(f"OK: report saved to {args.out} and {args.out_txt}")
    print(
        f"Files: {len(files)} | OK: {report['summary']['files_ok']} | "
        f"Skipped: {report['summary']['files_skipped']} | "
        f"Errors: {report['summary']['files_with_errors']} | Warn-only: {report['summary']['files_with_warnings_only']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
