
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class UserFacingError(Exception):
    """
    An error that is safe and useful to show directly in UI.
    """
    code: str
    message: str
    details: Optional[dict[str, Any]] = None
    stage: Optional[str] = None

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.stage:
            out["stage"] = self.stage
        if self.details:
            out["details"] = self.details
        return out
