from __future__ import annotations

import logging
import time

from src.report_pipeline.state import AgentState
from src.services.activity_template_service import list_agent_activity_templates
from src.domain.report.template_skill import merge_template_skill_order
from src.services.marketing_api_service import fetch_data_template_list

logger = logging.getLogger("activity-analysis.agent")


async def template_list_fetch_node(state: AgentState) -> dict:
    intent = state.get("marketing_intent") or {}
    t0 = time.monotonic()
    logger.info("数据模板列表获取开")
    result = fetch_data_template_list({"scene": intent.get("scene", "")})

    if result.success:
        templates = _normalize_template_source(result.data or [])
        logger.info("数据模板列表获取完成: templates=%d source=api (%.2fs)", len(templates), time.monotonic() - t0)
        return {
            "template_list": templates,
            "workflow_mode": "template_component_report",
            "next_agent": "supervisor",
        }

    managed_templates = _load_managed_templates()
    if not managed_templates:
        return {
            "next_agent": "finalize",
            "final_response": f"数据模板列表API调用失败：{result.error}",
        }

    logger.warning("外部数据模板列表API调用失败，使用本地活动分析数据模板继 %s", result.error)
    templates = _normalize_template_source(managed_templates)
    logger.info("数据模板列表获取完成: templates=%d source=local (%.2fs)", len(templates), time.monotonic() - t0)
    return {
        "template_list": templates,
        "workflow_mode": "template_component_report",
        "next_agent": "supervisor",
    }


def _load_managed_templates() -> list[dict]:
    try:
        templates = list_agent_activity_templates()
        logger.info("本地活动分析数据模板加载完成: templates=%d", len(templates))
        return templates
    except Exception as exc:
        logger.warning("本地活动分析数据模板加载失败，继续使用外部数据模板API: %s", str(exc))
        return []


def _normalize_template_source(templates: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen = set()
    for template in templates:
        normalized = merge_template_skill_order(template)
        key = (
            str(normalized.get("template_id") or normalized.get("code") or "").strip()
            or str(normalized.get("template_name") or normalized.get("name") or "").strip()
        )
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(normalized)
    return merged
