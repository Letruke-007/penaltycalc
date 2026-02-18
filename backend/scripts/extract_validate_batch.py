# backend/scripts/extract_validate_batch.py
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.pipeline.pdf_to_json import pdf_to_json


DEFAULT_RATE_PERCENT = 9.5
DEFAULT_CALC_DATE = "23.02.2026"
DEFAULT_CATEGORY = "Прочие"
DEFAULT_OVERDUE_START_DAY = 1


@dataclass
class OneResult:
    pdf: str
    ok: bool
    err_type: Optional[str] = None
    err_msg: Optional[str] = None
    traceback: Optional[str] = None
    # light stats
    charges: Optional[int] = None
    payments: Optional[int] = None


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_text(p: Path, txt: str) -> None:
    p.write_text(txt, encoding="utf-8")


def _write_json(p: Path, obj: Any) -> None:
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _iter_pdfs(pdf_dir: Path) -> List[Path]:
    if not pdf_dir.exists() or not pdf_dir.is_dir():
        raise SystemExit(f"--pdf-dir not found or not a directory: {pdf_dir}")
    pdfs = sorted([p for p in pdf_dir.rglob("*.pdf") if p.is_file()])
    return pdfs


def _call_pdf_to_json(
    pdf_path: Path,
    *,
    category: str,
    calc_date: str,
    rate_percent: float,
    overdue_start_day: int,
) -> Dict[str, Any]:
    """
    Wrapper: keep keyword args so the call is stable if you reorder params in pdf_to_json().
    """
    return pdf_to_json(
        str(pdf_path),
        category=category,
        calc_date=calc_date,
        rate_percent=rate_percent,
        overdue_start_day=overdue_start_day,
    )


def process_one(pdf_path: Path, *, category: str, calc_date: str, rate_percent: float, overdue_start_day: int,
                save_json_dir: Optional[Path]) -> OneResult:
    try:
        stmt = _call_pdf_to_json(
            pdf_path,
            category=category,
            calc_date=calc_date,
            rate_percent=rate_percent,
            overdue_start_day=overdue_start_day,
        )

        # optional: persist produced json for debugging
        if save_json_dir is not None:
            _ensure_dir(save_json_dir)
            out_json = save_json_dir / (pdf_path.stem + ".json")
            _write_json(out_json, stmt)

        charges_n = len(((stmt or {}).get("statement") or {}).get("charges") or [])
        payments_n = len(((stmt or {}).get("statement") or {}).get("payments") or [])

        return OneResult(pdf=str(pdf_path), ok=True, charges=charges_n, payments=payments_n)

    except Exception as e:  # noqa: BLE001
        return OneResult(
            pdf=str(pdf_path),
            ok=False,
            err_type=type(e).__name__,
            err_msg=str(e),
            traceback=traceback.format_exc(),
        )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="extract_validate_batch",
        description="Batch: PDF -> JSON (parser+validation). Writes per-file OK/ERROR and diagnostics.",
    )
    ap.add_argument("--pdf-dir", required=True, help="Directory with input PDFs (recursively).")
    ap.add_argument("--out", required=True, help="Output directory for reports.")
    ap.add_argument("--save-json", action="store_true", help="Also save produced JSON next to the report (for debugging).")

    # Deterministic defaults requested
    ap.add_argument("--rate-percent", type=float, default=DEFAULT_RATE_PERCENT, help="Key rate percent (default: 9.5).")
    ap.add_argument("--calc-date", type=str, default=DEFAULT_CALC_DATE, help="Calc date DD.MM.YYYY (default: 23.02.2026).")
    ap.add_argument("--category", type=str, default=DEFAULT_CATEGORY, help="Consumer category (default: Прочие).")
    ap.add_argument("--overdue-start-day", type=int, default=DEFAULT_OVERDUE_START_DAY, help="Overdue start day (default: 1).")

    args = ap.parse_args(argv)

    pdf_dir = Path(args.pdf_dir)
    out_dir = Path(args.out)
    _ensure_dir(out_dir)

    save_json_dir: Optional[Path] = (out_dir / "json") if args.save_json else None

    pdfs = _iter_pdfs(pdf_dir)
    started = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    results: List[OneResult] = []
    ok_cnt = 0
    err_cnt = 0

    # Console header
    print(f"[START] files={len(pdfs)} pdf_dir={pdf_dir}")
    print(f"  category={args.category} calc_date={args.calc_date} rate_percent={args.rate_percent} overdue_start_day={args.overdue_start_day}")
    print(f"  out={out_dir}")
    if args.save_json:
        print(f"  save_json_dir={save_json_dir}")

    for idx, p in enumerate(pdfs, start=1):
        rel = str(p.relative_to(pdf_dir))
        print(f"[{idx:03d}/{len(pdfs):03d}] {rel}")

        r = process_one(
            p,
            category=args.category,
            calc_date=args.calc_date,
            rate_percent=float(args.rate_percent),
            overdue_start_day=int(args.overdue_start_day),
            save_json_dir=save_json_dir,
        )
        results.append(r)

        if r.ok:
            ok_cnt += 1
            print(f"  ✓ OK (charges={r.charges}, payments={r.payments})")
        else:
            err_cnt += 1
            print(f"  ✗ ERROR {r.err_type}: {r.err_msg}")

            # write per-file traceback immediately (so progress isn't lost)
            safe_name = p.stem.replace(os.sep, "_").replace("/", "_")
            _write_text(out_dir / f"error_{safe_name}.traceback.txt", r.traceback or "")

    finished = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # Aggregated reports
    report = {
        "meta": {
            "started_at": started,
            "finished_at": finished,
            "pdf_dir": str(pdf_dir),
            "out_dir": str(out_dir),
            "category": args.category,
            "calc_date": args.calc_date,
            "rate_percent": float(args.rate_percent),
            "overdue_start_day": int(args.overdue_start_day),
            "files_total": len(pdfs),
            "ok": ok_cnt,
            "errors": err_cnt,
        },
        "files": [
            {
                "pdf": r.pdf,
                "ok": r.ok,
                "charges": r.charges,
                "payments": r.payments,
                "err_type": r.err_type,
                "err_msg": r.err_msg,
            }
            for r in results
        ],
    }

    _write_json(out_dir / "extract_report.json", report)

    # Human-readable summary
    lines: List[str] = []
    lines.append(f"FILES: {len(pdfs)} | OK: {ok_cnt} | ERROR: {err_cnt}")
    lines.append(f"category={args.category} calc_date={args.calc_date} rate_percent={args.rate_percent} overdue_start_day={args.overdue_start_day}")
    lines.append("")
    if err_cnt:
        lines.append("ERRORS:")
        for r in results:
            if r.ok:
                continue
            lines.append(f"- {Path(r.pdf).name}: {r.err_type}: {r.err_msg}")
    _write_text(out_dir / "extract_report.txt", "\n".join(lines) + "\n")

    print("[DONE]")
    print(f"OK: {ok_cnt} | ERROR: {err_cnt}")
    print(f"Report saved to: {out_dir / 'extract_report.json'}")
    return 0 if err_cnt == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
