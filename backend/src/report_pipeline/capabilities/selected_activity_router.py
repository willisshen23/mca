from __future__ import annotations

import logging

from src.report_pipeline.state import AgentState

logger = logging.getLogger("njbank.agent")


async def selected_activity_router_node(state: AgentState) -> dict:
    activities = state.get("activity_list") or []
    if not activities:
        return {"next_agent": "finalize", "final_response": "未选择活动，无法继续分析"}

    if len(activities) == 1:
        logger.info("活动选择路由: 单活动，优先查询外呼业务数据")
        return {
            "activity_list": activities,
            "activity_route_result": {
                "activity_count": 1,
                "route_type": "single_activity",
                "next_flow": "outbound_data_first",
                "summary": "单活动分析处理",
            },
            "workflow_mode": "single_activity_outbound_first",
            "next_agent": "supervisor",
        }

    logger.info("活动选择路由: 多活动，进入数据模板组件分析流程 activities=%d", len(activities))
    return {
        "activity_list": activities,
        "activity_route_result": {
            "activity_count": len(activities),
            "route_type": "multi_activity",
            "next_flow": "template_component_report",
            "summary": "多活动分析处理",
        },
        "workflow_mode": "template_component_report",
        "outbound_activity_data_found": False,
        "next_agent": "supervisor",
    }
