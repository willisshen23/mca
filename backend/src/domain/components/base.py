from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AnalysisComponent(ABC):
    type: str
    display_name: str
    config_schema: dict[str, Any]

    @abstractmethod
    def get_analysis_prompt(self, component: dict, data_summary: str) -> str: ...

    @abstractmethod
    def get_report_prompt(self, component: dict, analysis_result: str) -> str: ...
