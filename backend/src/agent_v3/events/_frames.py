"""SSE 帧构造函数（从 agent_v2/events/sse_bridge.py 逐字平移）。

帧契约与 v2 完全一致，前端零改动：
裸 `data: {json}\n\n`，事件类型在 JSON type 字段内（前端只解析 data: 行）。
node_update 帧结构（type/payload/node/node_display_name/progress_message）不变，
前端 UiChatView.vue 的 trace 面板逻辑可零改动复用。

只保留 v3 sse_bridge / rails 实际消费的构造函数与常量；v2 专属的
stream_events / approval_required_frame / _resolve_activity_approvals /
frame 已随 agent_v2 包一并删除。
"""
from __future__ import annotations

import json
from datetime import date, datetime
from datetime import time as datetime_time
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote

from src.agent_v3.tools import TOOL_DISPLAY_NAMES

# 管线步骤进度文案（拷贝自旧 graph_run_service.NODE_PROGRESS_MESSAGE，
# 保持前端 trace 面板在两种 Agent 下观感一致）
PIPELINE_PROGRESS_MESSAGE = {
    "selected_activity_router": "正在判断单活多活动分析分支...",
    "outbound_activity_data_fetch": "正在查询单个外呼活动业务数据...",
    "template_list_fetch": "正在加载可用的分析能力...",
    "template_matching": "正在结合活动数据，实时匹配所需的分析维度与指标组件...",
    "component_value_fetch": "正在获取组件指标和业务数据...",
    "component_value_cleanup": "正在清理组件值中的空字段...",
    "activity_template_matching": "正在依据活动特征编排报告结构与分析组件...",
    "uploaded_component_value_extract": "正在按活动模板整理上传文件中的组件指标数据...",
    "marketing_report_synthesis": "正在生成活动分析报告...",
}

PIPELINE_STEP_DISPLAY_NAME = {
    "selected_activity_router": "活动查询与选择",
    "outbound_activity_data_fetch": "外呼活动数据查询",
    "template_list_fetch": "分析能力准备",
    "template_matching": "分析组件匹配",
    "component_value_fetch": "组件数值获取",
    "component_value_cleanup": "组件值清理",
    "activity_template_matching": "报告框架编排",
    "uploaded_component_value_extract": "上传活动指标整理",
    "marketing_report_synthesis": "报告生成",
}

_SUMMARY_LIMIT = 120


def _json_safe(value):
    if isinstance(value, (datetime, date, datetime_time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def _frame(message: dict) -> str:
    return f"data: {json.dumps(_json_safe(message), ensure_ascii=False, default=str)}\n\n"


def tool_progress_frame(tool: str, status: str, summary: str = "", args_summary: dict | None = None) -> str:
    display = TOOL_DISPLAY_NAMES.get(tool, tool)
    if status == "running":
        progress = f"正在{display}..."
    else:
        progress = f"{display}完成：{summary}" if summary else f"{display}完成"
    payload: dict[str, Any] = {"tool_status": status}
    if args_summary:
        payload["args_summary"] = args_summary
    message = {
        "type": "node_update",
        "node": tool,
        "node_display_name": display,
        "progress_message": progress,
        "payload": payload,
    }
    return _frame(message)


def pipeline_step_frame(step: str, status: str) -> str:
    if status == "running":
        progress = PIPELINE_PROGRESS_MESSAGE.get(step, f"正在执行 {step}...")
    else:
        display = PIPELINE_STEP_DISPLAY_NAME.get(step, step)
        progress = f"{display}完成"
    message = {
        "type": "node_update",
        "node": step,
        "node_display_name": PIPELINE_STEP_DISPLAY_NAME.get(step, step),
        "progress_message": progress,
        "payload": {"tool_status": status},
    }
    return _frame(message)


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content or "")


def _compact_report_context(report_context: dict) -> dict:
    if not isinstance(report_context, dict):
        return {}
    compact = {k: v for k, v in report_context.items() if k != "data_snapshot"}
    return compact


def _export_artifact(formatted_output_path: Any) -> dict:
    """将内部导出路径转换为前端可安全使用的下载元数据。"""
    if not formatted_output_path:
        return {}
    file_name = Path(str(formatted_output_path)).name
    extension = Path(file_name).suffix.lower().lstrip(".")
    if not file_name or extension != "html":
        return {}
    return {
        "kind": "report_export",
        "file_name": file_name,
        "format": extension,
        "download_url": f"/report-exports/{quote(file_name)}",
    }


def _args_summary(args: Any) -> dict:
    if not isinstance(args, dict):
        return {}
    summary = {}
    for key, value in args.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, str) and len(value) > 60:
            summary[key] = value[:60] + "…"
        else:
            summary[key] = value
    return summary


def _summarize_content(content: Any) -> str:
    text = _message_text(content)
    # 工具结果多为 JSON；提炼关键字段，避免把整包 JSON 塞进进度条
    if text.startswith("ERROR:"):
        return text[:_SUMMARY_LIMIT]
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            for key in ("note", "count", "status", "activities", "activity_template"):
                if key in parsed:
                    value = parsed[key]
                    if isinstance(value, (str, int)):
                        return str(value)[:_SUMMARY_LIMIT]
    except (ValueError, TypeError):
        pass
    return text[:_SUMMARY_LIMIT]
