"""分析队列工具 impl：add_to_analysis_queue / remove_from_analysis_queue / update_analysis_config。

队列是 Agent 内部状态，不直接修改银行系统活动。写入操作均经人机确认。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.agent_v3.prompts.perspectives import get_perspective, perspective_keys_text
from src.agent_v3.tools.impl import ToolContext, ToolOutcome
from src.agent_v3.tools.impl.common import (
    activity_key,
    activity_name,
    error_content,
    ok_content,
)

logger = logging.getLogger("njbank.agent")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_perspective(perspective: str) -> str:
    key = (perspective or "").strip()
    if not key:
        return ""
    if get_perspective(key) is None:
        raise ValueError(f"无效的分析视角：{key}。可选视角：{perspective_keys_text()}")
    return key


def _find_in_state(state: dict, activity_id: str) -> dict | None:
    for item in state.get("activity_list") or []:
        if isinstance(item, dict) and activity_key(item) == activity_id:
            return item
    return None


async def add_to_analysis_queue(
    ctx: ToolContext,
    activity_ids: list[str],
    perspective: str = "",
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
) -> str | ToolOutcome:
    """将已核实活动加入待分析队列。"""
    if not activity_ids:
        return error_content("activity_ids 不能为空")

    try:
        perspective = _validate_perspective(perspective)
    except ValueError as exc:
        return error_content(str(exc))

    state = ctx.state
    existing_queue = state.get("analysis_queue") or []
    existing_ids = {item.get("activity_id") for item in existing_queue if isinstance(item, dict)}

    added: list[dict] = []
    skipped: list[str] = []
    not_found: list[str] = []
    new_queue = list(existing_queue)

    for raw_id in activity_ids:
        activity_id = (raw_id or "").strip()
        if not activity_id:
            continue
        if activity_id in existing_ids:
            skipped.append(activity_id)
            continue

        snapshot = _find_in_state(state, activity_id)
        verified = snapshot is not None
        if not verified:
            not_found.append(activity_id)

        item = {
            "activity_id": activity_id,
            "name": activity_name(snapshot) if snapshot else activity_id,
            "channel": snapshot.get("channel") if snapshot else "",
            "activity_type": snapshot.get("activity_type") if snapshot else "",
            "added_at": _now_iso(),
            "verified": verified,
            "config": {
                "perspective": perspective,
                "metrics": list(metrics or []),
                "dimensions": list(dimensions or []),
            },
        }
        new_queue.append(item)
        existing_ids.add(activity_id)
        added.append(item)

    note_parts = []
    if added:
        note_parts.append(f"已加入 {len(added)} 个活动")
    if skipped:
        note_parts.append(f"{len(skipped)} 个活动已在队列中")
    if not_found:
        note_parts.append(f"{len(not_found)} 个活动未在最近查询结果中找到，已标记为未核实")
    note = "；".join(note_parts) or "队列无变化"

    content = ok_content(
        {
            "status": "ok",
            "added": added,
            "skipped": skipped,
            "not_found": not_found,
            "queue_length": len(new_queue),
            "note": note,
        }
    )
    return ToolOutcome(content, {"analysis_queue": new_queue})


async def remove_from_analysis_queue(
    ctx: ToolContext,
    activity_ids: list[str],
) -> str | ToolOutcome:
    """将指定活动移出当前会话的待分析队列。"""
    if not activity_ids:
        return error_content("activity_ids 不能为空")

    state = ctx.state
    queue = state.get("analysis_queue") or []
    remove_set = {str(a).strip() for a in activity_ids if str(a).strip()}
    new_queue = [
        item
        for item in queue
        if isinstance(item, dict) and item.get("activity_id") not in remove_set
    ]
    removed_count = len(queue) - len(new_queue)

    content = ok_content(
        {
            "status": "ok",
            "removed_count": removed_count,
            "queue_length": len(new_queue),
            "note": f"已移除 {removed_count} 个活动" if removed_count else "指定活动不在队列中",
        }
    )
    return ToolOutcome(content, {"analysis_queue": new_queue})


async def update_analysis_config(
    ctx: ToolContext,
    activity_id: str,
    perspective: str = "",
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
) -> str | ToolOutcome:
    """调整分析队列中某个活动的分析配置（指标/维度/视角）。"""
    activity_id = (activity_id or "").strip()
    if not activity_id:
        return error_content("activity_id 不能为空")

    try:
        perspective = _validate_perspective(perspective)
    except ValueError as exc:
        return error_content(str(exc))

    state = ctx.state
    queue = state.get("analysis_queue") or []
    found = False
    new_queue = []
    updated_config: dict = {}

    for item in queue:
        if isinstance(item, dict) and item.get("activity_id") == activity_id:
            config = dict(item.get("config") or {})
            if perspective:
                config["perspective"] = perspective
            if metrics is not None:
                config["metrics"] = list(metrics)
            if dimensions is not None:
                config["dimensions"] = list(dimensions)
            item = {**item, "config": config}
            updated_config = config
            found = True
        new_queue.append(item)

    if not found:
        return error_content(f"活动 {activity_id} 不在分析队列中")

    content = ok_content(
        {
            "status": "ok",
            "activity_id": activity_id,
            "config": updated_config,
            "queue_length": len(new_queue),
            "note": f"已更新 {activity_id} 的分析配置",
        }
    )
    return ToolOutcome(content, {"analysis_queue": new_queue})
