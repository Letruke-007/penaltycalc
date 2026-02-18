from __future__ import annotations

import re
from typing import Iterable, List

_WS_RE = re.compile(r"[ \t\u00A0]+")  # включая NBSP
_TRAIL_RE = re.compile(r"[ \t\u00A0]+$")


def normalize_line(s: str) -> str:
    s = s.replace("\r", "")
    s = _WS_RE.sub(" ", s)
    s = _TRAIL_RE.sub("", s)
    return s.strip()


def normalize_lines(lines: Iterable[str]) -> List[str]:
    out: List[str] = []
    for ln in lines:
        ln = normalize_line(ln)
        if ln != "":
            out.append(ln)
    return out
