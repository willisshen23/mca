from __future__ import annotations

import logging
import time

from src.report_pipeline.state import AgentState
from src.services.marketing_api_service import fetch_outbound_activity_data

logger = logging.getLogger("activity-analysis.agent")


async def outbound_activity_data_fetch_node(state: AgentState) -> dict:
    activities = state.get("activity_list") or []
    if len(activities) != 1:
        return {
            "workflow_mode": "template_component_report",
            "outbound_activity_data_found": False,
            "next_agent": "supervisor",
        }

    activity = activities[0]
    activity_id = activity.get("act_no") or activity.get("activity_id") or activity.get("活动编号") or ""
    if not activity_id:
        return {
            "workflow_mode": "template_component_report",
            "outbound_activity_data_found": False,
            "next_agent": "supervisor",
        }

    t0 = time.monotonic()
    logger.info("外呼活动业务数据查询开 activity_id=%s", activity_id)
    result = fetch_outbound_activity_data(
        {
            "act_no": activity_id,
            "activity_id": activity_id,
            "activity": activity,
            "user_id": state.get("user_id") or "",
            "org_no": state.get("org_no") or "",
            "channel": state.get("channel") or "",
        }
    )
    if not result.success:
        return {
            "next_agent": "finalize",
            "final_response": f"外呼活动查询API调用失败：{result.error}",
        }

    data = result.data or {}
    found = bool(data and not (isinstance(data, dict) and data.get("matched") is False))
    logger.info(
        "外呼活动业务数据查询完成: activity_id=%s found=%s (%.2fs)",
        activity_id,
        found,
        time.monotonic() - t0,
    )

    if not found:
        return {
            "outbound_activity_data": {},
            "outbound_activity_data_found": False,
            "workflow_mode": "template_component_report",
            "next_agent": "supervisor",
        }

    return {
        "outbound_activity_data": data,
        "outbound_activity_data_found": True,
        "workflow_mode": "direct_outbound_report",
        "plan": _skip_template_component_steps(state.get("plan") or []),
        "next_agent": "supervisor",
    }


def _skip_template_component_steps(plan: list[dict]) -> list[dict]:
    skip_steps = {
        "template_list_fetch",
        "template_matching",
        "component_value_fetch",
        "component_value_cleanup",
    }
    for step in plan:
        if step.get("step") in skip_steps and step.get("status") == "pending":
            step["status"] = "done"
            step["skip_reason"] = "single_activity_outbound_data_found"
    return plan
