from __future__ import annotations

import sys
from pathlib import Path

# Гарантируем импорт app/, даже если запуск из корня репо
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.pipeline.orchestrator import run_batch


def main() -> None:
    """
    Простейший batch-запуск:
      python batch_extract.py <pdf_dir> <out_dir>

    Никакого CLI-фреймворка, только проверка аргументов.
    """
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python batch_extract.py <pdf_dir> <out_dir>")
        sys.exit(1)

    pdf_dir = sys.argv[1]
    out_dir = sys.argv[2]

    print(f"[INFO] PDF dir: {pdf_dir}")
    print(f"[INFO] OUT dir: {out_dir}")

    report = run_batch(pdf_dir, out_dir)

    print()
    print("[RESULT]")
    print(f"  total: {report['count_total']}")
    print(f"  ok:    {report['count_ok']}")
    print(f"  fail:  {report['count_fail']}")
    print(f"  report saved to: {Path(out_dir) / 'batch_report.json'}")


if __name__ == "__main__":
    main()
