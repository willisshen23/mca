"""报告导出工具 impl：export_report（从 agent_v2/tools/report_export.py 平移，去框架依赖）。

与 v2 的差异（P3 去旧框架依赖）：
- runtime → ToolContext（ctx.state 取 html_report/report_context/request_id）；
- pydantic args_schema 降级为普通关键字入参（校验由壳层工具 schema 负责）；
- 成功路径返回 ToolOutcome（state_updates 替代 tool_command/Command）。

行为边界（M3 决策，原样保留）：当前仅支持 HTML 导出，
非 html 格式一律返回 "ERROR: 当前仅支持导出 HTML"。
"""
from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from pathlib import Path

from src.agent_v3.tools.impl import ToolContext, ToolOutcome
from src.agent_v3.tools.impl.common import error_content, ok_content
from src.config import get_settings
from src.services.report_export_service import write_report_html

logger = logging.getLogger("activity-analysis.agent")


def _safe_filename(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r'[\\/:*?"<>|\r\n]+', "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:80]


async def export_report(
    ctx: ToolContext,
    format: str = "html",
    output_filename: str = "",
) -> str | ToolOutcome:
    """将当前报告导出为 HTML 文件。"""
    format = (format or "html").lower().strip()
    if format != "html":
        return error_content("当前仅支持导出 HTML")

    state = ctx.state
    html = state.get("html_report") or ""
    report_context = state.get("report_context") or {}
    if not html:
        return error_content("当前没有可导出的报告")

    report_id = report_context.get("report_id") or ctx.request.request_id or "unknown"
    base_name = _safe_filename(output_filename) or f"report-{report_id}"

    settings = get_settings()
    export_dir = settings.report_export_dir or ""
    if export_dir:
        from src.config import resolve_path
        out_dir = resolve_path(export_dir)
    else:
        out_dir = Path(tempfile.gettempdir()) / "activity-analysis_exports"
    out_dir.mkdir(parents=True, exist_ok=True)

    output_path = str(out_dir / f"{base_name}.{format}")
    try:
        path = await asyncio.to_thread(
            write_report_html,
            html,
            output_path,
        )
    except Exception as exc:
        logger.exception("export_report failed")
        return error_content(f"导出 {format.upper()} 失败：{exc}")

    content = ok_content(
        {
            "status": "ok",
            "format": format,
            "file_name": Path(path).name,
            "download_ready": True,
            "note": f"{format.upper()} 报告已成功导出，前端将显示下载按钮。",
        }
    )
    return ToolOutcome(
        content,
        {"formatted_output_path": path},
    )
