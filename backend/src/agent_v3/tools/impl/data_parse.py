"""数据解析工具 impl：parse_uploaded_data。

复用旧 activity_file_parse_node，将上传文件标准化为 uploaded_activity_dataset
与 activity_list，供 generate_report(data_source="uploaded") 使用。
"""
from __future__ import annotations

import asyncio
import logging

from src.agent_v3.tools.impl import ToolContext, ToolOutcome
from src.agent_v3.tools.impl.common import error_content, ok_content
from src.report_pipeline.capabilities.activity_file_parse import activity_file_parse_node
from src.services.uploaded_file_service import summarize_uploaded_file

logger = logging.getLogger("njbank.agent")


async def parse_uploaded_data(ctx: ToolContext, confirm: bool = True) -> str | ToolOutcome:
    """解析用户当前上传的活动数据文件，生成结构化数据集和活动列表。"""
    file_path = (ctx.request.uploaded_file_path or "").strip()
    if not file_path:
        return error_content("没有上传文件，请先上传活动数据文件")

    state = ctx.state
    existing = state.get("uploaded_activity_dataset") or {}
    if existing.get("activities"):
        return ok_content(
            {
                "status": "ok",
                "file_name": existing.get("file_name"),
                "activities": len(existing["activities"]),
                "note": "上传数据已解析，可直接生成报告",
            }
        )

    seed = {
        "uploaded_file_path": file_path,
        "request_id": ctx.request.request_id or "",
    }
    try:
        update = await asyncio.to_thread(activity_file_parse_node, seed)
    except Exception as exc:
        logger.exception("parse_uploaded_data failed")
        return error_content(f"解析上传文件失败：{exc}")

    if update.get("next_agent") == "finalize":
        return error_content(update.get("final_response") or "解析失败")

    dataset = update.get("uploaded_activity_dataset") or {}
    activities = update.get("activity_list") or []
    if not activities:
        return error_content("未从上传文件中识别到活动记录")

    try:
        data_summary = await asyncio.to_thread(summarize_uploaded_file, file_path)
    except Exception:
        data_summary = ""
    dataset["data_summary"] = data_summary

    content = ok_content(
        {
            "status": "ok",
            "file_name": dataset.get("file_name"),
            "total_rows": dataset.get("total_rows", 0),
            "activities": len(activities),
            "note": f"已解析 {len(activities)} 条活动记录，可基于上传数据生成报告",
        }
    )
    return ToolOutcome(
        content,
        {
            "uploaded_activity_dataset": dataset,
            "activity_list": activities,
            "data_summary": data_summary,
        },
    )
