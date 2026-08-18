"""报告查看与修改工具 impl：get_report_content / modify_report（从 agent_v2/tools/report_modify.py 平移，去框架依赖）。

与 v2 的差异（P3 去旧框架依赖）：
- runtime → ToolContext（ctx.state 取 html_report/report_context）；
- LLM 调用由 get_llm + asyncio.to_thread(llm.invoke, ...) 改为
  get_model + 直接 await model.invoke(...)（工具本身已在 async 上下文）；
- pydantic args_schema 降级为普通关键字入参（校验由壳层工具 schema 负责）；
- 成功路径返回 ToolOutcome（state_updates 替代 tool_command/Command）。
"""
from __future__ import annotations

import logging
import re
from uuid import uuid4

from bs4 import BeautifulSoup

from src.report_pipeline.capabilities.report_html_guard import (
    REPORT_HTML_GUARD_FAILURE_MESSAGE,
    validate_report_html,
)
from src.report_pipeline.capabilities.report_layout_guard import (
    auto_fix_chart_layout,
    normalize_content_card_layout,
    normalize_metric_card_layout,
)
from src.report_pipeline.capabilities.utils import extract_html_content, fix_echarts_scripts
from src.agent_v3.tools.impl import ToolContext, ToolOutcome
from src.agent_v3.tools.impl.common import error_content, ok_content
from src.config import get_settings
from src.llm import get_model
from src.services.agent_run_history_service import save_report_file

logger = logging.getLogger("njbank.agent")


async def get_report_content(ctx: ToolContext, summary_length: int = 2000) -> str | ToolOutcome:
    """获取当前已生成报告的 HTML 文本摘要与版本信息，供 modify_report 前的审视使用。"""
    state = ctx.state
    html = state.get("html_report") or ""
    report_context = state.get("report_context") or {}
    if not html:
        return error_content("当前没有已生成的报告")

    summary = _extract_text_summary(html, summary_length)
    content = ok_content(
        {
            "status": "ok",
            "report_id": report_context.get("report_id"),
            "version": report_context.get("version", 1),
            "html_chars": len(html),
            "text_summary": summary,
            "note": "当前报告摘要已获取，请基于摘要提出修改建议",
        }
    )
    return ToolOutcome(content, {"report_context": report_context})


async def modify_report(
    ctx: ToolContext,
    content_changes: list[str] | None = None,
    chart_replacements: list[dict] | None = None,
    style_changes: list[str] | None = None,
    free_instruction: str = "",
) -> str | ToolOutcome:
    """基于当前报告 HTML 和用户结构化修改指令，生成修改后的新版本报告。"""
    state = ctx.state
    html = state.get("html_report") or ""
    report_context = state.get("report_context") or {}
    if not html:
        return error_content("当前没有可修改的报告")

    instruction = _build_modification_instruction(
        content_changes or [],
        chart_replacements or [],
        style_changes or [],
        free_instruction,
    )
    if not instruction.strip():
        return error_content("缺少修改指令")

    model = get_model("report_generation", temperature=0.2)
    prompt = _build_modify_prompt(html, instruction, report_context)

    try:
        response = await model.invoke(prompt)
    except Exception as exc:
        return error_content(f"修改报告时模型调用失败：{exc}")

    new_html = _postprocess_html(response.content)
    max_retries = max(0, int(get_settings().report_html_guard_max_retries))
    guard_result = None
    for attempt in range(max_retries + 1):
        guard_result = validate_report_html(new_html)
        if guard_result.valid:
            break
        if attempt == max_retries:
            return error_content(
                f"修改后的报告未通过展示校验：{REPORT_HTML_GUARD_FAILURE_MESSAGE}"
            )
        retry_prompt = (
            prompt
            + "\n\n重要：上一次输出未通过展示检查，问题包括："
            + "；".join(issue.message for issue in guard_result.issues)
            + "。请重新输出完整 HTML 文档。"
        )
        response = await model.invoke(retry_prompt)
        new_html = _postprocess_html(response.content)

    report_id = report_context.get("report_id") or uuid4().hex
    _asset_name, version_no = save_report_file(
        report_id,
        new_html,
        source="modify",
        change_note=instruction[:500],
    )

    new_version = (report_context.get("version") or 1) + 1
    history = list(report_context.get("history") or [])
    history.append(
        {
            "version": new_version,
            "action": "modify",
            "diff_summary": instruction,
            "previous_report_id": report_context.get("report_id"),
        }
    )
    new_report_context = {
        "report_id": report_id,
        "request_id": report_id,
        "file_path": f"activity-analysis-report-{report_id}.html",
        "version": new_version,
        "version_no": version_no,
        "history": history,
        "perspective": report_context.get("perspective", ""),
        "status": "active",
        "data_snapshot": report_context.get("data_snapshot", {}),
    }

    content = ok_content(
        {
            "status": "ok",
            "report_id": report_id,
            "version": new_version,
            "version_no": version_no,
            "html_chars": len(new_html),
            "note": "报告已修改并通过展示校验",
        }
    )
    return ToolOutcome(
        content,
        {
            "html_report": new_html,
            "report_context": new_report_context,
            "report_html_guard_result": guard_result.to_dict(
                retry_count=attempt, max_retries=max_retries
            ),
        },
    )


def _build_modification_instruction(
    content_changes: list[str],
    chart_replacements: list[dict],
    style_changes: list[str],
    free_instruction: str,
) -> str:
    parts = []
    if content_changes:
        parts.append("内容修改：" + "；".join(content_changes))
    if chart_replacements:
        items = []
        for item in chart_replacements:
            cid = item.get("chart_id") or "未指定"
            to_type = item.get("to_chart_type") or "未指定"
            items.append(f"将 {cid} 替换为 {to_type}")
        parts.append("图表替换：" + "；".join(items))
    if style_changes:
        parts.append("样式调整：" + "；".join(style_changes))
    if free_instruction:
        parts.append(f"其他要求：{free_instruction}")
    return "\n".join(parts)


def _build_modify_prompt(html: str, instruction: str, report_context: dict) -> str:
    perspective = report_context.get("perspective", "")
    perspective_hint = f"\n- 保持分析视角：{perspective}" if perspective else ""
    return f"""你是一名银行营销活动报告编辑助手。请根据用户要求修改下面这份 HTML 报告，并输出完整、可直接展示的 HTML 文档。

当前 HTML 报告：
{html}

修改要求：
{instruction}

约束：
- 保持原有报告结构、数据完整性和 ECharts 图表可用；
- 仅做要求的修改，不要无理由删减其他内容；
- 输出完整 HTML（含 <!DOCTYPE html>、<html lang="zh-CN">、<head>、<meta charset="UTF-8">、<body>）；
- 页面 body 内必须有可见主标题；
- ECharts 脚本必须可执行，禁止输出裸对象字面量；
- 不要输出 Markdown、代码块围栏或解释性前后缀。{perspective_hint}
"""


def _postprocess_html(raw: str) -> str:
    html = extract_html_content(raw)
    html = fix_echarts_scripts(html)
    html = auto_fix_chart_layout(html)
    html = normalize_metric_card_layout(html)
    html = normalize_content_card_layout(html)
    return html


def _extract_text_summary(html: str, limit: int) -> str:
    try:
        soup = BeautifulSoup(html, "html.parser")
        for script in soup.find_all("script"):
            script.decompose()
        for style in soup.find_all("style"):
            style.decompose()
        text = soup.get_text(" ", strip=True)
    except Exception:
        text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= limit else text[:limit] + "…"
