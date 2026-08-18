"""模板查询工具 impl：get_available_templates。

包装 services/activity_template_service.list_agent_activity_templates
（自带 DB session，返回 agent-ready 字典）。
"""
from __future__ import annotations

import asyncio
import logging

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.common import error_content, ok_content, summarize
from src.services.activity_template_service import list_agent_activity_templates

logger = logging.getLogger("njbank.agent")


async def get_available_templates(ctx: ToolContext, template_type: str = "", keyword: str = "") -> str:
    """查询可用的分析报告模板（含模板包含的分析技能列表）。"""
    try:
        templates = await asyncio.to_thread(list_agent_activity_templates, template_type, keyword)
    except Exception as exc:
        logger.warning("get_available_templates 查询异常: %s", str(exc)[:200])
        return error_content(f"模板查询异常：{summarize(str(exc), 120)}")

    if not templates:
        return error_content("未查询到符合条件的分析模板")

    compacted = [
        {
            "template_id": t.get("template_id") or t.get("code") or "",
            "template_name": t.get("template_name") or t.get("name") or "",
            "type": t.get("type") or "",
            "desc": t.get("template_desc") or t.get("desc") or "",
            "skills": t.get("skills") or [],
            "useCnt": t.get("useCnt", 0),
        }
        for t in templates
        if isinstance(t, dict)
    ]
    return ok_content({"count": len(compacted), "templates": compacted})
