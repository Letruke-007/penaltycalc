#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strict JSON comparator for pdf2xlsx-app.

Compares generated JSON files against etalon JSON files 1:1 (deep structural equality).
- generated dir: backend/out/generated_json
- etalon dir:    backend/out/etalon_json
Filenames must match.

Outputs:
- JSON report (machine-readable)
- TXT report (human-readable)
Exit codes:
- 0: all OK
- 2: diffs found / missing files / extras
- 3: unexpected error
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional


@dataclass
class Diff:
    path: str
    kind: str  # TYPE_MISMATCH | VALUE_MISMATCH | MISSING_KEY | EXTRA_KEY | LENGTH_MISMATCH
    expected: Any
    actual: Any


def _short(v: Any, limit: int = 300) -> Any:
    # Keep the report readable: truncate long strings / large objects
    try:
        s = json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        s = str(v)
    if len(s) <= limit:
        return v
    return s[:limit] + "…"


def _cmp(expected: Any, actual: Any, path: str, diffs: List[Diff], max_diffs: int) -> None:
    if len(diffs) >= max_diffs:
        return

    if expected is None or actual is None:
        if expected != actual:
            diffs.append(Diff(path, "VALUE_MISMATCH", _short(expected), _short(actual)))
        return

    te, ta = type(expected), type(actual)
    if te != ta:
        diffs.append(Diff(path, "TYPE_MISMATCH", te.__name__, ta.__name__))
        return

    if isinstance(expected, dict):
        exp_keys = set(expected.keys())
        act_keys = set(actual.keys())
        missing = sorted(exp_keys - act_keys)
        extra = sorted(act_keys - exp_keys)
        for k in missing:
            if len(diffs) >= max_diffs:
                return
            diffs.append(Diff(f"{path}.{k}" if path else k, "MISSING_KEY", _short(expected.get(k)), "<missing>"))
        for k in extra:
            if len(diffs) >= max_diffs:
                return
            diffs.append(Diff(f"{path}.{k}" if path else k, "EXTRA_KEY", "<missing>", _short(actual.get(k))))
        for k in sorted(exp_keys & act_keys):
            if len(diffs) >= max_diffs:
                return
            _cmp(expected[k], actual[k], f"{path}.{k}" if path else k, diffs, max_diffs)
        return

    if isinstance(expected, list):
        if len(expected) != len(actual):
            diffs.append(Diff(path, "LENGTH_MISMATCH", len(expected), len(actual)))
            return
        for i, (e_item, a_item) in enumerate(zip(expected, actual)):
            if len(diffs) >= max_diffs:
                return
            _cmp(e_item, a_item, f"{path}[{i}]", diffs, max_diffs)
        return

    # primitives
    if expected != actual:
        diffs.append(Diff(path, "VALUE_MISMATCH", _short(expected), _short(actual)))


def compare_files(etalon_path: str, generated_path: str, max_diffs: int) -> Tuple[bool, List[Diff], Optional[str]]:
    try:
        with open(etalon_path, "r", encoding="utf-8") as f:
            etalon = json.load(f)
        with open(generated_path, "r", encoding="utf-8") as f:
            generated = json.load(f)
    except Exception as e:
        return False, [], f"JSON_READ_ERROR: {e}"

    diffs: List[Diff] = []
    _cmp(etalon, generated, "", diffs, max_diffs=max_diffs)
    ok = len(diffs) == 0
    return ok, diffs, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare generated JSON with etalon JSON (strict 1:1).")
    ap.add_argument("--generated-dir", default="backend/out/generated_json", help="Directory with generated JSON")
    ap.add_argument("--etalon-dir", default="backend/out/etalon_json", help="Directory with etalon JSON")
    ap.add_argument("--out-json", default="backend/out/json_compare_report.json", help="Output JSON report path")
    ap.add_argument("--out-txt", default="backend/out/json_compare_report.txt", help="Output TXT report path")
    ap.add_argument("--max-diffs-per-file", type=int, default=200, help="Cap diffs per file in report")
    ap.add_argument("--only", default="", help="Optional substring filter for filenames (e.g. contract no)")
    args = ap.parse_args()

    gen_dir = args.generated_dir
    eta_dir = args.etalon_dir

    if not os.path.isdir(gen_dir):
        raise SystemExit(f"generated-dir not found: {gen_dir}")
    if not os.path.isdir(eta_dir):
        raise SystemExit(f"etalon-dir not found: {eta_dir}")

    gen_files = {f for f in os.listdir(gen_dir) if f.lower().endswith(".json")}
    eta_files = {f for f in os.listdir(eta_dir) if f.lower().endswith(".json")}

    if args.only:
        gen_files = {f for f in gen_files if args.only in f}
        eta_files = {f for f in eta_files if args.only in f}

    missing_generated = sorted(eta_files - gen_files)
    extra_generated = sorted(gen_files - eta_files)
    common = sorted(eta_files & gen_files)

    results: Dict[str, Any] = {
        "generated_dir": gen_dir,
        "etalon_dir": eta_dir,
        "summary": {
            "total_etalon": len(eta_files),
            "total_generated": len(gen_files),
            "common": len(common),
            "missing_generated": len(missing_generated),
            "extra_generated": len(extra_generated),
            "ok": 0,
            "fail": 0,
            "errors": 0,
        },
        "missing_generated": missing_generated,
        "extra_generated": extra_generated,
        "files": [],
    }

    lines: List[str] = []
    lines.append("JSON compare report (strict 1:1)")
    lines.append(f"Etalon:    {eta_dir}")
    lines.append(f"Generated: {gen_dir}")
    if args.only:
        lines.append(f"Filter:    {args.only}")
    lines.append("")

    for fn in common:
        ep = os.path.join(eta_dir, fn)
        gp = os.path.join(gen_dir, fn)
        ok, diffs, err = compare_files(ep, gp, max_diffs=args.max_diffs_per_file)

        entry: Dict[str, Any] = {"file": fn, "ok": ok, "error": err, "diffs": []}
        if err:
            results["summary"]["errors"] += 1
            lines.append(f"[ERROR] {fn}: {err}")
        elif ok:
            results["summary"]["ok"] += 1
            lines.append(f"[OK]    {fn}")
        else:
            results["summary"]["fail"] += 1
            lines.append(f"[FAIL]  {fn}  diffs={len(diffs)} (showing up to {args.max_diffs_per_file})")
            for d in diffs[:args.max_diffs_per_file]:
                entry["diffs"].append(
                    {"path": d.path, "kind": d.kind, "expected": d.expected, "actual": d.actual}
                )
                lines.append(f"   - {d.kind}: {d.path}")
                lines.append(f"       expected: {d.expected}")
                lines.append(f"       actual:   {d.actual}")

        results["files"].append(entry)

    # Missing/extras section
    if missing_generated:
        lines.append("")
        lines.append("Missing in generated:")
        for fn in missing_generated:
            lines.append(f"  - {fn}")

    if extra_generated:
        lines.append("")
        lines.append("Extra in generated:")
        for fn in extra_generated:
            lines.append(f"  - {fn}")

    # Write outputs
    os.makedirs(os.path.dirname(args.out_json), exist_ok=True)
    os.makedirs(os.path.dirname(args.out_txt), exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with open(args.out_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # Console summary
    lines2 = []
    lines2.append("")
    lines2.append(
        f"Summary: etalon={len(eta_files)} generated={len(gen_files)} "
        f"common={len(common)} ok={results['summary']['ok']} "
        f"fail={results['summary']['fail']} errors={results['summary']['errors']} "
        f"missing={len(missing_generated)} extra={len(extra_generated)}"
    )
    lines2.append(f"Report: {args.out_json}")
    lines2.append(f"Text:   {args.out_txt}")
    print("\n".join(lines2))

    if missing_generated or extra_generated or results["summary"]["fail"] or results["summary"]["errors"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"FATAL: {e}")
        raise SystemExit(3)
