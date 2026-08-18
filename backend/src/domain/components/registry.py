from __future__ import annotations

from typing import Any
from .base import AnalysisComponent


class ComponentRegistry:
    _components: dict[str, AnalysisComponent] = {}

    @classmethod
    def register(cls, component: AnalysisComponent) -> None:
        cls._components[component.type] = component

    @classmethod
    def get(cls, comp_type: str) -> AnalysisComponent:
        if comp_type not in cls._components:
            raise KeyError(f"Unknown component type: {comp_type}")
        return cls._components[comp_type]

    @classmethod
    def list_all(cls) -> list[dict[str, Any]]:
        return [
            {
                "type": c.type,
                "display_name": c.display_name,
                "config_schema": c.config_schema,
            }
            for c in cls._components.values()
        ]

    @classmethod
    def get_types(cls) -> list[str]:
        return list(cls._components.keys())
