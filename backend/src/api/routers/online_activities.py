from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from src.services.marketing_api_service import fetch_activity_list

logger = logging.getLogger("activity-analysis.agent")

router = APIRouter(prefix="/online-activities")


def _serialize_activity(item: dict) -> dict:
    """映射为前端活动列表所需字段。"""
    return {
        "actNo": item.get("act_no") or "",
        "name": item.get("name") or "",
        "type": item.get("activity_type") or item.get("actTypeCd") or "",
        "start": item.get("start_date") or item.get("actStartDt") or "",
        "end": item.get("end_date") or item.get("actEndDt") or "",
        "goal": item.get("goal") or "",
        "status": item.get("status") or item.get("actStatusCd") or "",
        "channel": item.get("channel") or "",
    }


@router.get("")
async def api_list_online_activities(
    keyword: str = Query(default=""),
    activity_type: str = Query(default=""),
    start_date: str = Query(default=""),
    end_date: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
):
    started = time.perf_counter()
    params = {
        "keyword": keyword.strip(),
        "actTypeCd": activity_type.strip(),
        "start_date": start_date.strip(),
        "end_date": end_date.strip(),
        "pageNum": page,
        "pageSize": page_size,
    }
    result = await run_in_threadpool(fetch_activity_list, params)
    if not result.success:
        logger.warning("online_activities_api query failed: %s", result.error)
        raise HTTPException(status_code=502, detail=result.error or "活动列表查询失败")

    activities = [
        _serialize_activity(item)
        for item in result.data or []
        # 上游可能返回无名称/编号的空记录，直接过滤
        if (item.get("name") or "").strip() or (item.get("act_no") or "").strip()
    ]
    # 上游只返回当前页数组、无总数，用"返回条数 == page_size"判断是否还有下一页
    has_more = len(activities) >= page_size
    logger.info(
        "online_activities_api list keyword=%r page=%d page_size=%d count=%d cost_ms=%.2f",
        params["keyword"],
        page,
        page_size,
        len(activities),
        (time.perf_counter() - started) * 1000,
    )
    return {
        "activities": activities,
        "page": page,
        "page_size": page_size,
        "has_more": has_more,
    }
