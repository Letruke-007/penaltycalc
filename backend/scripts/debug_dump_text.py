from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.extract.pdf_reader import read_pdf_pages


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python debug_dump_text.py <pdf_path> [--lines N]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    n = 250
    if "--lines" in sys.argv:
        i = sys.argv.index("--lines")
        if i + 1 < len(sys.argv):
            n = int(sys.argv[i + 1])

    pages = read_pdf_pages(pdf_path)
    all_lines = []
    for p in pages:
        all_lines.extend(p.lines)

    print(f"[INFO] pages={len(pages)} lines={len(all_lines)}")
    print("----- FIRST LINES -----")
    for ln in all_lines[:n]:
        print(ln)


if __name__ == "__main__":
    main()
