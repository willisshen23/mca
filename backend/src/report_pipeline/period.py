"""分析周期计算：数据模板接口的起止日期统一口径（设计文档 §5.2）。

规则：
- start_date = 全部活动最早开始时间；
- 存在未结束活动（end_date 为空/无法解析/>= today）→ end_date = today - 2；
- 均已结束 → end_date = 最晚 end_date；
- T-2 早于 start_date 时钳制为 start_date，避免起止倒挂。
"""
from __future__ import annotations

import re
from datetime import date, timedelta

_START_FIELDS = ("actStartDt", "start_date", "startDate", "活动开始日期")
_END_FIELDS = ("actEndDt", "end_date", "endDate", "活动结束日期")


def compute_analysis_period(activities: list[dict], today: date) -> dict:
    starts = [d for a in activities if (d := _parse_date(_first(a, _START_FIELDS)))]
    ends = [d for a in activities if (d := _parse_date(_first(a, _END_FIELDS)))]
    start = min(starts) if starts else None
    if any(_is_ongoing(a, today) for a in activities):
        end = today - timedelta(days=2)
        if start and end < start:
            end = start
    else:
        end = max(ends) if ends else None
    return {
        "start_date": start.isoformat() if start else "",
        "end_date": end.isoformat() if end else "",
    }


def _first(activity: dict, fields: tuple[str, ...]) -> str:
    for field in fields:
        value = str(activity.get(field) or "").strip()
        if value:
            return value
    return ""


def _is_ongoing(activity: dict, today: date) -> bool:
    raw = _first(activity, _END_FIELDS)
    if not raw:
        return True
    parsed = _parse_date(raw)
    if parsed is None:
        return True  # 无法解析的结束日期按未结束处理，避免误取远期日期
    return parsed >= today


def _parse_date(raw: str) -> date | None:
    match = re.match(r"^(\d{4})[-/]?(\d{2})[-/]?(\d{2})", raw.strip())
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
