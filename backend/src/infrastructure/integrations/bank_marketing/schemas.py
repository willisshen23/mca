from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ApiResult:
    success: bool
    data: Any = None
    error: str = ""
    meta: dict = field(default_factory=dict)
