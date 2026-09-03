"""活动查询工具 impl：search_activities / get_activity_detail。

包装 services/marketing_api_service.fetch_activity_list（dict -> ApiResult），
供应商字段映射与别名处理均在客户端内部完成。
"""
from __future__ import annotations

import asyncio
import logging

from src.agent_v3.tools.impl import ToolContext, ToolOutcome
from src.agent_v3.tools.impl.common import (
    activity_key,
    compact_activity,
    error_content,
    ok_content,
    summarize,
)
from src.services.marketing_api_service import fetch_activity_list

logger = logging.getLogger("activity-analysis.agent")

_MAX_ACTIVITIES = 50


def _fetch_activities_with_retry(params: dict):
    """网络类错误自动重试 1 次（设计文档 §9.1）。"""
    result = fetch_activity_list(params)
    if not result.success:
        logger.info("search_activities 首次查询失败，重试一次: %s", result.error[:120])
        result = fetch_activity_list(params)
    return result


async def search_activities(
    ctx: ToolContext,
    keyword: str = "",
    activity_type: str = "",
    channel: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 20,
) -> str | ToolOutcome:
    """按关键词/渠道/日期等条件查询银行营销活动，返回活动列表。"""
    params: dict = {"limit": min(max(limit, 1), _MAX_ACTIVITIES)}
    request = ctx.request
    if request.user_id:
        params["userNo"] = request.user_id
    if request.src_sys_no:
        params["srcSysNo"] = request.src_sys_no
    if keyword:
        params["actName"] = keyword
    if activity_type:
        params["actTypeCd"] = activity_type
    if channel:
        params["channel"] = channel
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    try:
        result = await asyncio.to_thread(_fetch_activities_with_retry, params)
    except Exception as exc:  # 客户端内部异常（网络/解析）
        logger.warning("search_activities 查询异常: %s", str(exc)[:200])
        return error_content(f"活动查询接口调用异常：{summarize(str(exc), 120)}")

    if not result.success:
        return error_content(f"活动查询接口返回失败：{summarize(result.error, 120)}")

    raw_items = result.data if isinstance(result.data, list) else []
    seen: set[str] = set()
    compacted: list[dict] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        compact = compact_activity(item)
        key = compact["activity_id"] or compact["name"]
        if key in seen:
            continue
        seen.add(key)
        compacted.append(compact)
        if len(compacted) >= _MAX_ACTIVITIES:
            break

    # 查询结果序号是本次结果集内的稳定定位符，方便用户使用
    # “第 2 行”或“第 1、3 行”选择活动。真正执行工具时仍使用 activity_id。
    for row_number, activity in enumerate(compacted, start=1):
        activity["row_number"] = row_number

    if not compacted:
        return error_content("未查询到符合条件的活动，建议放宽关键词或日期范围后重试")

    content = ok_content(
        {
            "count": len(compacted),
            "activities": compacted[: max(1, min(limit, _MAX_ACTIVITIES))],
            "note": (
                "已按条件查询到活动。展示列表时每行必须保留 row_number 序号；"
                "用户可按一个或多个序号选择，后续工具调用需将序号映射为对应 activity_id"
            ),
        }
    )
    # 同一轮请求内多次按名查询的结果合并由壳层在写入会话时执行（merge_keys 标记）：
    # impl 读到的 state 快照可能早于并行调用的写入，在此处做读-改-写合并会丢活动。
    return ToolOutcome(
        content,
        {"activity_list": compacted, "activity_list_request_id": ctx.request.request_id},
        merge_keys=("activity_list",),
    )


async def get_activity_detail(ctx: ToolContext, activity_id: str) -> str:
    """查看单个活动的详细信息。优先使用最近查询结果，未命中则回源查询。"""
    activity_id = (activity_id or "").strip()
    if not activity_id:
        return error_content("activity_id 不能为空")

    state = ctx.state
    for item in state.get("activity_list") or []:
        if isinstance(item, dict) and activity_key(item) == activity_id:
            return ok_content({"activity": item, "source": "recent_search"})

    try:
        params = {"actName": activity_id}
        request = ctx.request
        if request.user_id:
            params["userNo"] = request.user_id
        if request.src_sys_no:
            params["srcSysNo"] = request.src_sys_no
        result = await asyncio.to_thread(fetch_activity_list, params)
    except Exception as exc:
        return error_content(f"活动详情查询接口异常：{summarize(str(exc), 120)}")

    if not result.success:
        return error_content(f"活动详情查询接口返回失败：{summarize(result.error, 120)}")

    for item in result.data if isinstance(result.data, list) else []:
        if isinstance(item, dict):
            compact = compact_activity(item)
            if compact["activity_id"] == activity_id:
                return ok_content({"activity": compact, "source": "bank_api"})

    return error_content(f"未找到活动 {activity_id}，请先用 search_activities 查询核实")
