"""技能查询工具 impl：get_available_skills。

包装 services/skill_service.list_skills，返回系统中所有启用的分析
skill（不限于已加入分析模板的 skill）。
"""
from __future__ import annotations

import asyncio
import logging

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.common import error_content, ok_content, summarize
from src.infrastructure.db.session import SessionLocal
from src.services.skill_service import list_skills, serialize_skill

logger = logging.getLogger("activity-analysis.agent")


def _list_agent_skills(category: str = "", keyword: str = "") -> list[dict]:
    db = SessionLocal()
    try:
        skills = [serialize_skill(skill) for skill in list_skills(db, keyword=keyword)]
        clean_category = (category or "").strip()
        if clean_category:
            skills = [s for s in skills if clean_category in (s.get("cat") or "")]
        return skills
    finally:
        db.close()


async def get_available_skills(ctx: ToolContext, category: str = "", keyword: str = "") -> str:
    """查询系统中所有可用的分析 skill（分析组件），不限于已加入分析模板的 skill。"""
    try:
        skills = await asyncio.to_thread(_list_agent_skills, category, keyword)
    except Exception as exc:
        logger.warning("get_available_skills 查询异常: %s", str(exc)[:200])
        return error_content(f"分析 skill 查询异常：{summarize(str(exc), 120)}")

    if not skills:
        return error_content("未查询到符合条件的分析 skill")

    compacted = [
        {
            "id": s.get("id"),
            "code": s.get("code") or "",
            "name": s.get("name") or "",
            "category": s.get("cat") or "",
            "desc": s.get("desc") or "",
            "version": s.get("version") or "",
            "useCnt": s.get("useCnt", 0),
        }
        for s in skills
        if isinstance(s, dict)
    ]
    return ok_content({"count": len(compacted), "skills": compacted})
