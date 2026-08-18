from __future__ import annotations

import logging
from typing import Any

from src.report_pipeline.state import AgentState
from src.services.uploaded_file_service import read_uploaded_activity_records

logger = logging.getLogger("njbank.agent")

ACTIVITY_ID_KEYS = ("activity_id", "act_no", "actNo", "活动编号", "活动ID", "活动id")
ACTIVITY_NAME_KEYS = ("activity_name", "name", "act_name", "actName", "活动名称", "活动")
START_DATE_KEYS = ("start_date", "startDate", "actStartDt", "活动开始日", "开始日")
END_DATE_KEYS = ("end_date", "endDate", "actEndDt", "活动结束日期", "结束日期")
TYPE_KEYS = ("activity_type", "actTypeCd", "活动类型", "类型")
CHANNEL_KEYS = ("channel", "渠道", "渠道编码")
GOAL_KEYS = ("goal", "target", "活动运营目标", "活动目标", "目标")


def activity_file_parse_node(state: AgentState) -> dict:
    file_path = state.get("uploaded_file_path", "")
    if not file_path:
        return {"next_agent": "finalize", "final_response": "未找到上传文件，无法解析活动数据"}

    try:
        file_data = read_uploaded_activity_records(file_path, max_rows=500)
    except Exception as exc:
        logger.warning("activity_file_parse failed: %s", exc)
        return {"next_agent": "finalize", "final_response": f"上传活动数据解析失败: {exc}"}

    records = file_data.get("records") or []
    activities = [_normalize_activity(record, index) for index, record in enumerate(records, start=1)]
    dataset = {
        "source": "uploaded_file",
        "file_name": file_data.get("file_name", ""),
        "file_type": file_data.get("file_type", ""),
        "headers": file_data.get("headers", []),
        "total_rows": file_data.get("total_rows", len(records)),
        "sample_records": records[:10],
        "activities": activities,
    }
    logger.info(
        "activity_file_parse completed: rows=%d normalized_activities=%d",
        dataset["total_rows"],
        len(activities),
    )
    return {
        "uploaded_activity_dataset": dataset,
        "activity_list": activities,
        "report_history_enabled": True,
        "next_agent": "supervisor",
    }


def _normalize_activity(record: dict[str, Any], index: int) -> dict[str, Any]:
    activity_id = _first_value(record, ACTIVITY_ID_KEYS) or f"uploaded-{index}"
    activity_name = _first_value(record, ACTIVITY_NAME_KEYS) or f"上传活动{index}"
    return {
        "activity_id": str(activity_id),
        "name": str(activity_name),
        "activity_name": str(activity_name),
        "start_date": _first_value(record, START_DATE_KEYS),
        "end_date": _first_value(record, END_DATE_KEYS),
        "activity_type": _first_value(record, TYPE_KEYS),
        "channel": _first_value(record, CHANNEL_KEYS),
        "goal": _first_value(record, GOAL_KEYS),
        "source": "uploaded_file",
        "raw": record,
    }


def _first_value(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lower_map = {str(key).lower(): value for key, value in record.items()}
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
        value = lower_map.get(key.lower())
        if value not in (None, ""):
            return value
    return ""
