"""FastAPI router for 外呼活动 (outbound campaign) mock API."""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query

try:
    from .outbound_api2_router import router as outbound_api2_router
    from .waihu_data_service import get_activity_by_id, reload_data, search_activities
    from .waihu_schemas import (
        WaihuActivityDetail,
        WaihuActivityDetailResponse,
        WaihuActivityListResponse,
    )
except ImportError:
    from outbound_api2_router import router as outbound_api2_router
    from waihu_data_service import get_activity_by_id, reload_data, search_activities
    from waihu_schemas import (
        WaihuActivityDetail,
        WaihuActivityDetailResponse,
        WaihuActivityListResponse,
    )

logger = logging.getLogger("mock.waihu")

router = APIRouter(tags=["外呼活动"])
router.include_router(outbound_api2_router)


@router.get("/waihu/activities", response_model=WaihuActivityListResponse)
async def api_list_waihu_activities(
    q: str = Query(default="", description="活动名称模糊查询关键词"),
    limit: int = Query(default=50, ge=1, le=200, description="返回条数上限"),
):
    """列出外呼活动（支持按活动名称模糊搜索）.

    - **q**: 查询关键词（空字符串返回所有活动）
    - **limit**: 最多返回多少条记录
    """
    started = time.perf_counter()
    activities = search_activities(q)
    total = len(activities)
    activities = activities[:limit]

    logger.info(
        "waihu_activity_search q=%r total=%d returned=%d cost_ms=%.2f",
        q,
        total,
        len(activities),
        (time.perf_counter() - started) * 1000,
    )
    return {"total": total, "activities": activities}


@router.get("/waihu/activities/{act_no}", response_model=WaihuActivityDetailResponse)
async def api_get_waihu_activity(act_no: str):
    """根据活动编号查询外呼活动详情.

    - **act_no**: 活动编号
    """
    started = time.perf_counter()
    record = get_activity_by_id(act_no)
    if record is None:
        logger.warning("waihu_activity_get not_found act_no=%s", act_no)
        raise HTTPException(status_code=404, detail="活动不存在")

    detail = WaihuActivityDetail(**record)
    logger.info(
        "waihu_activity_get act_no=%s cost_ms=%.2f",
        act_no,
        (time.perf_counter() - started) * 1000,
    )
    return {"success": True, "act_no": act_no, "data": detail}


@router.post("/waihu/reload")
async def api_reload_waihu_data():
    """强制重新加载外呼活动 Excel 数据（开发调试用）."""
    started = time.perf_counter()
    records = reload_data()
    logger.info(
        "waihu_data_reload count=%d cost_ms=%.2f",
        len(records),
        (time.perf_counter() - started) * 1000,
    )
    return {"status": "reloaded", "count": len(records)}
