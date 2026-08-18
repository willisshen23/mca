from __future__ import annotations

import logging
import re
import time
from typing import Any

from src.report_pipeline.capabilities.report_html_guard import build_report_html_retry_instruction
from src.report_pipeline.capabilities.report_layout_guard import (
    auto_fix_chart_layout,
    normalize_content_card_layout,
    normalize_metric_card_layout,
)
from src.report_pipeline.capabilities.utils import extract_html_content, fix_echarts_scripts
from src.domain.report.html_template import strip_report_footer_note
from src.llm import get_model
from src.report_pipeline.state import AgentState
from src.report_pipeline.prompts.marketing_workflow import MARKETING_REPORT_SYNTHESIS_PROMPT
from src.services.agent_run_history_service import create_report_run_history, update_prompt_text
from src.services.system_prompt_service import format_runtime_prompt
from src.domain.report.template_skill import (
    build_report_sections,
    sanitize_display_requirement,
    unwrap_component_values,
)

logger = logging.getLogger("njbank.agent")


async def marketing_report_synthesis_node(state: AgentState) -> dict:
    component_values = state.get("component_values") or {}
    outbound_data = state.get("outbound_activity_data") or {}
    report_values = outbound_data if state.get("workflow_mode") == "direct_outbound_report" else component_values
    if not report_values:
        return {"next_agent": "finalize", "final_response": "组件数值为空，无法生成分析报告"}

    t0 = time.monotonic()
    logger.info("Agent2综合报告生成开")
    data_template_match = state.get("template_match_result") or {"data_source": "outbound_activity_data"}
    activity_template_match = state.get("activity_template_match_result") or data_template_match
    report_sections = build_report_sections(activity_template_match, report_values)
    prompt_data_template_match = _compact_data_template_match(state)
    prompt_activity_template_match = _compact_activity_template_match(activity_template_match)
    prompt_report_sections = _compact_report_sections(report_sections)
    prompt_report_data = unwrap_component_values(report_values)
    prompt_text = format_runtime_prompt(
        "marketing_report_synthesis",
        MARKETING_REPORT_SYNTHESIS_PROMPT,
        user_text=_report_user_text(state),
        intent=_compact_intent(state.get("marketing_intent") or {}),
        activities=_compact_activities(state.get("activity_list") or []),
        data_template_match=prompt_data_template_match,
        activity_template_match=prompt_activity_template_match,
        report_sections=prompt_report_sections,
        report_data=prompt_report_data,
    )
    prompt_text += build_report_html_retry_instruction(state)
    create_report_run_history(state)
    update_prompt_text(state.get("request_id", ""), prompt_text)
    model = get_model("report_generation", temperature=0.1)
    logger.debug("Agent2报告生成提示词：%s", prompt_text)
    logger.info("Agent2报告生成提示词准备完 chars=%d", len(prompt_text))
    response = await model.invoke(prompt_text)
    logger.debug("Agent2报告生成原始响应: %s", response.content)
    logger.info("Agent2报告生成原始响应长度: size=%d", len(response.content or ""))

    html_report = extract_html_content(response.content)
    html_report = fix_echarts_scripts(html_report)
    html_report = auto_fix_chart_layout(html_report)
    html_report = normalize_metric_card_layout(html_report)
    html_report = normalize_content_card_layout(html_report)
    html_report = _remove_report_footer_note(html_report)
    html_report = _remove_template_instruction_text(html_report)
    if "<" not in html_report or ">" not in html_report:
        logger.warning("Agent2返回内容不是HTML，使用保底HTML报告")
        html_report = _fallback_html_report(state)

    logger.info("Agent2综合报告生成完成: HTML长度 %d (%.2fs)", len(html_report), time.monotonic() - t0)
    return {
        "html_report": html_report,
        "final_response": f"{'本次请求'} 活动分析报告已生成",
        "next_agent": "supervisor",
        "report_history_enabled": False,
        "selected_report_activity_ids": [],
    }


def _fallback_html_report(state: AgentState) -> str:
    activities = state.get("activity_list") or []
    data_template_match = state.get("template_match_result") or {}
    activity_template_match = state.get("activity_template_match_result") or data_template_match
    component_values = state.get("component_values") or {}
    outbound_data = state.get("outbound_activity_data") or {}
    report_values = outbound_data if state.get("workflow_mode") == "direct_outbound_report" else component_values
    report_sections = build_report_sections(activity_template_match, report_values)
    activity_items = "".join(
        f"<li>{activity.get('name', '')} ({activity.get('channel', '')}, {activity.get('goal', '')})</li>"
        for activity in activities
    )
    supported_sections = [
        section for section in report_sections
        if _has_report_value(section.get("values"))
    ]
    section_items = "".join(
        f"""
  <section>
    <h2>{section.get('position')}. {section.get('skill_name')}</h2>
    <p>组件：{section.get('component_id')}</p>
    <pre>{section.get('values')}</pre>
  </section>
"""
        for section in supported_sections
    )
    if section_items:
        body_html = f"""
  <h2>活动模板 SKILL 组件执行顺序</h2>
  {section_items}
  <h2>生成说明</h2>
  <p>以上内容仅基于已返回且可匹配到模板章节的数据生成，未返回数据的模板章节已跳过。</p>
"""
    else:
        body_html = """
  <h2>生成说明</h2>
  <p>当前报告数据不足以支撑活动报告模板中的章节要求，未生成分析章节。</p>
"""
    return f"""
<section class="bank-report">
  <h1>活动分析报告</h1>
  <p>匹配数据模板：{data_template_match.get('template_name', '')}</p>
  <p>匹配活动模板：{activity_template_match.get('template_name', '')}</p>
  <h2>分析活动</h2>
  <ul>{activity_items}</ul>
  {body_html}
</section>
"""


def _has_report_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float, bool)):
        return True
    if isinstance(value, list):
        return any(_has_report_value(item) for item in value)
    if isinstance(value, dict):
        return any(_has_report_value(item) for item in value.values())
    return bool(value)


def _remove_report_footer_note(html: str) -> str:
    return strip_report_footer_note(html)


def _remove_template_instruction_text(html: str) -> str:
    if not html:
        return html
    instruction_pattern = (
        r"(?:可视化建议|图表建议|展示建议|建议使用(?:柱状图|折线图|饼图|漏斗图|表格)|"
        r"本章节应展示|需要展示|展示方式|输出要求|字段说明)"
        r"[:：][^<\n\r]*"
    )
    html = re.sub(
        rf"\s*<(p|li|div|span)\b[^>]*>\s*{instruction_pattern}\s*</\1>\s*",
        "",
        html,
        flags=re.IGNORECASE,
    )
    return re.sub(rf"^[ \t]*{instruction_pattern}[ \t]*(?:\r?\n)?", "", html, flags=re.IGNORECASE | re.MULTILINE)


def _latest_user_text(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""
    message = messages[-1]
    # v3 seed 用纯 dict 消息；历史消息对象按属性兜底取 content
    if isinstance(message, dict):
        text = str(message.get("content") or "")
    else:
        text = str(getattr(message, "content", "") or "")
    return text.strip()


def _report_user_text(state: AgentState) -> str:
    original = str(state.get("original_user_text") or "").strip()
    return original or _latest_user_text(state)


def _compact_intent(intent: dict[str, Any]) -> dict[str, Any]:
    return _clean_dict(
        {
            "intent_type": intent.get("intent_type"),
            "activity_type": intent.get("activity_type"),
            "period": intent.get("period"),
            "scene": intent.get("scene"),
        }
    )


def _compact_activities(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for activity in activities:
        compacted = _clean_dict(
            {
                "activity_id": _first_value(activity, "activity_id", "act_no", "actNo", "活动编号"),
                "activity_name": _first_value(activity, "activity_name", "name", "act_name", "actName", "活动名称"),
                "channel": _first_value(activity, "channel", "渠道"),
                "start_date": _first_value(activity, "start_date", "startDate", "begin_date", "活动开始时"),
                "end_date": _first_value(activity, "end_date", "endDate", "finish_date", "活动结束时间"),
                "goal": _first_value(activity, "goal", "target", "活动运营目标"),
            }
        )
        # activity_type 必须显式传递，避免 LLM 在缺失时自行推测为"外呼活动"
        activity_type = _first_value(activity, "activity_type", "actTypeCd", "活动类型")
        if not activity_type:
            channel = _first_value(activity, "channel", "渠道")
            activity_type = _derive_activity_type_from_channel(channel)
        compacted["activity_type"] = activity_type
        result.append(compacted)
    return result


def _derive_activity_type_from_channel(channel: str) -> str:
    """当活动数据缺少 activity_type 时，从渠道字段推导活动类型标签。"""
    if not channel:
        return ""
    cl = channel.strip()
    if "短信" in cl:
        return "短信活动"
    if "外呼" in cl or "电话" in cl or "呼叫" in cl:
        return "外呼活动"
    if "APP" in cl or "app" in cl or "推送" in cl:
        return "APP推送活动"
    if "微信" in cl or "H5" in cl or "h5" in cl:
        return "微信/H5活动"
    if "线下" in cl or "网点" in cl or "门店" in cl:
        return "线下活动"
    if "线上" in cl:
        return "线上活动"
    return ""


def _compact_data_template_match(state: AgentState) -> dict[str, Any]:
    if (
        state.get("workflow_mode") == "direct_outbound_report"
        or state.get("workflow_key") == "uploaded_activity_report"
        or state.get("uploaded_activity_dataset")
    ):
        return {"matched_templates": []}

    match_result = state.get("template_match_result") or {}
    component_values = state.get("component_values") or {}
    candidates = (
        state.get("matched_data_templates")
        or component_values.get("matched_data_templates")
        or match_result.get("matched_data_templates")
        or ([match_result] if match_result else [])
    )
    time_range = _time_range_from_state(state)
    templates = []
    seen = set()
    for item in candidates:
        if not isinstance(item, dict):
            continue
        template_id = str(item.get("template_id") or item.get("code") or item.get("id") or "").strip()
        template_name = str(item.get("template_name") or item.get("name") or "").strip()
        key = template_id or template_name
        if not key or key in seen:
            continue
        seen.add(key)
        templates.append(
            _clean_dict(
                {
                    "template_id": template_id,
                    "template_name": template_name,
                    "time_range": _time_range_from_template(item) or time_range,
                }
            )
        )
    return {"matched_templates": templates}


def _compact_activity_template_match(match_result: dict[str, Any]) -> dict[str, Any]:
    return _clean_dict(
        {
            "template_id": match_result.get("template_id"),
            "template_name": match_result.get("template_name"),
            "activity_ids": match_result.get("activity_ids"),
            "reasoning": match_result.get("reasoning"),
        }
    )


def _compact_report_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact_sections = []
    for section in sections:
        display_requirement = sanitize_display_requirement(
            section.get("display_requirement") or section.get("skill_template_preview") or ""
        )
        compact_sections.append(
            _clean_dict(
                {
                    "position": section.get("position"),
                    "skill_name": section.get("skill_name"),
                    "component_id": section.get("component_id"),
                    "metrics": section.get("metrics"),
                    "skill_description": section.get("skill_description"),
                    "display_requirement": display_requirement,
                }
            )
        )
    return compact_sections


def _time_range_from_template(template: dict[str, Any]) -> dict[str, Any]:
    for key in ("time_range", "date_range", "period"):
        value = template.get(key)
        if isinstance(value, dict):
            return _clean_dict(
                {
                    "start_date": _first_value(value, "start_date", "startDate", "begin_date"),
                    "end_date": _first_value(value, "end_date", "endDate", "finish_date"),
                }
            )
    return _clean_dict(
        {
            "start_date": _first_value(template, "start_date", "startDate", "begin_date"),
            "end_date": _first_value(template, "end_date", "endDate", "finish_date"),
        }
    )


def _time_range_from_state(state: AgentState) -> dict[str, Any]:
    intent = state.get("marketing_intent") or {}
    period = intent.get("period") if isinstance(intent.get("period"), dict) else {}
    params = state.get("activity_query_params") or {}
    return _clean_dict(
        {
            "start_date": _first_value(period, "start_date", "startDate", "begin_date")
            or _first_value(params, "start_date", "startDate", "begin_date"),
            "end_date": _first_value(period, "end_date", "endDate", "finish_date")
            or _first_value(params, "end_date", "endDate", "finish_date"),
        }
    )


def _first_value(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _clean_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {})}
