"""活动模板数据加载服务."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("mock.template")

_JSON_PATH: Path = Path(__file__).parent / "活动模板清单接口.txt"
_data_cache: list[dict[str, Any]] | None = None


def load_template_data() -> list[dict[str, Any]]:
    """从 JSON 文件加载活动模板数据.

    Returns:
        List of template record dicts (原始字段).
    """
    global _data_cache
    if _data_cache is not None:
        return _data_cache

    if not _JSON_PATH.exists():
        logger.error("Template JSON file not found: %s", _JSON_PATH)
        return []

    try:
        with _JSON_PATH.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse template JSON: %s", exc)
        return []

    rows = payload.get("rows", [])
    _data_cache = rows
    logger.info("Loaded %d template records from %s", len(rows), _JSON_PATH.name)
    return rows


def reload_template_data() -> list[dict[str, Any]]:
    """强制重新加载模板数据."""
    global _data_cache
    _data_cache = None
    return load_template_data()
