from __future__ import annotations

import logging
from typing import Any

from src.report_pipeline.state import AgentState

logger = logging.getLogger("njbank.agent")

EMPTY_STRINGS = {"", "none", "null", "undefined", "nan"}


async def component_value_cleanup_node(state: AgentState) -> dict:
    component_values = state.get("component_values") or {}
    component_value_params = state.get("component_value_params") or {}

    cleaned_values, removed_value_count = _clean_value(component_values)
    cleaned_params, removed_param_count = _clean_value(component_value_params)

    logger.info(
        "component_value_cleanup completed: removed_values=%d removed_params=%d",
        removed_value_count,
        removed_param_count,
    )
    logger.debug(
        "component_value_cleanup cleaned_data: component_values=%s component_value_params=%s",
        cleaned_values,
        cleaned_params,
    )

    return {
        "component_values": cleaned_values if isinstance(cleaned_values, dict) else {},
        "component_value_params": cleaned_params if isinstance(cleaned_params, dict) else {},
        "component_value_cleanup_result": {
            "removed_values": removed_value_count,
            "removed_params": removed_param_count,
        },
        "next_agent": "supervisor",
    }


def _clean_value(value: Any) -> tuple[Any, int]:
    if isinstance(value, dict):
        cleaned: dict[Any, Any] = {}
        removed = 0
        for key, item in value.items():
            cleaned_item, item_removed = _clean_value(item)
            removed += item_removed
            if _is_empty(cleaned_item):
                removed += 1
                continue
            cleaned[key] = cleaned_item
        return cleaned, removed

    if isinstance(value, list):
        cleaned_items = []
        removed = 0
        for item in value:
            cleaned_item, item_removed = _clean_value(item)
            removed += item_removed
            if _is_empty(cleaned_item):
                removed += 1
                continue
            cleaned_items.append(cleaned_item)
        return cleaned_items, removed

    return value, 0


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in EMPTY_STRINGS
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) == 0
    return False
