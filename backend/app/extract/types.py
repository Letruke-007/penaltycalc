from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class PageText:
    page_index: int
    text: str
    lines: List[str]
