from __future__ import annotations
from src.report_pipeline.capabilities.utils import raise_if_run_cancelled

import logging
import time
from typing import Any

from src.config import extract_json
from src.llm import get_model
from src.infrastructure.db.models import ActivityAnalysisTemplate
from src.infrastructure.db.session import SessionLocal
from src.report_pipeline.state import AgentState
from src.report_pipeline.prompts.marketing_workflow import ACTIVITY_TEMPLATE_MATCHING_PROMPT
from src.services.activity_template_service import (
    get_template_by_code,
    increment_template_usage_by_code,
    list_agent_activity_templates,
)
from src.services.agent_run_history_service import ensure_report_run_history, record_template_match
from src.services.skill_service import record_skill_component_usage
from src.services.system_prompt_service import format_runtime_prompt
from src.domain.report.template_skill import apply_template_skill_order

logger = logging.getLogger("activity-analysis.agent")


async def activity_template_matching_node(state: AgentState) -> dict:
    raise_if_run_cancelled()  # 插话/停止后旧管线尽快中止，勿再烧 LLM 调用
    activities = state.get("activity_list") or []
    component_values = state.get("component_values") or {}
    uploaded_dataset = state.get("uploaded_activity_dataset") or {}
    is_uploaded_report = _is_uploaded_file_report_context(state)
    if is_uploaded_report:
        template_context_values = uploaded_dataset
        data_template_match = {}
    else:
        template_context_values = (
            (state.get("outbound_activity_data") or component_values)
            if state.get("workflow_mode") == "direct_outbound_report"
            else component_values
        )
        data_template_match = state.get("template_match_result") or {}

    if not activities:
        return {"next_agent": "finalize", "final_response": "未选择活动，无法匹配活动模板"}
    if (
        not template_context_values
        and state.get("workflow_mode") != "direct_outbound_report"
        and not is_uploaded_report
    ):
        return {"next_agent": "finalize", "final_response": "未获取到组件数据，无法匹配活动模板"}

    t0 = time.monotonic()
    all_activity_templates = _load_activity_templates()
    activity_templates = _filter_templates_for_context(all_activity_templates, state, activities)
    if not activity_templates:
        return {"next_agent": "finalize", "final_response": "未获取到管理界面中的活动模板，无法生成报告"}

    logger.info(
        "活动报告模板匹配开 activities=%d templates=%d filtered_from=%d outbound_context=%s",
        len(activities),
        len(activity_templates),
        len(all_activity_templates),
        _is_outbound_report_context(state, activities),
    )
    try:
        model = get_model("report_generation")
        response = await model.invoke(
            format_runtime_prompt(
                "activity_template_matching",
                ACTIVITY_TEMPLATE_MATCHING_PROMPT,
                activities=activities,
                data_template_match=data_template_match,
                component_values=template_context_values,
                activity_templates=activity_templates,
            )
        )
        logger.debug("活动报告模板匹配原始响应: %s", response.content)
        logger.info("活动报告模板匹配原始响应长度: size=%d", len(response.content or ""))
        match_result = extract_json(response.content)
    except Exception as exc:
        logger.warning("活动报告模板匹配失败，使用保底匹 %s", str(exc))
        match_result = _fallback_match(activities, activity_templates)

    match_result = apply_template_skill_order(match_result, activity_templates, activities)
    match_result["source"] = "activity_template_management"
    logger.info(
        "活动报告模板匹配完成: template_id=%s (%.2fs)",
        match_result.get("template_id", ""),
        time.monotonic() - t0,
    )
    try:
        template_code = match_result.get("template_id") or ""
        activity_template = _load_activity_template_by_code(template_code) if template_code else None

        top_data_template_name = None
        matched_data_templates = state.get("matched_data_templates") or []
        if matched_data_templates:
            top_data_template_name = matched_data_templates[0].get("template_name")

        request_id = state.get("request_id")
        thread_id = state.get("thread_id")
        if activity_template and request_id:
            ensure_report_run_history(str(request_id), str(thread_id or ""))
            record_template_match(str(request_id), activity_template, top_data_template_name)
            increment_template_usage_by_code(activity_template.code)
            record_skill_component_usage(
                _skill_usage_refs(match_result),
                request_id=str(request_id),
                source_type="activity_template",
                source_id=activity_template.id,
                source_code=activity_template.code,
                scene="activity_analysis",
                used_by=str(state.get("user_id") or ""),
            )
    except Exception as exc:
        logger.warning(
            "活动报告模板匹配埋点失败: request_id=%s error=%s",
            state.get("request_id", ""),
            str(exc),
        )

    return {
        "activity_template_list": activity_templates,
        "activity_template_match_result": match_result,
        "next_agent": "supervisor",
    }


def _load_activity_templates() -> list[dict[str, Any]]:
    return list_agent_activity_templates()


def _load_activity_template_by_code(code: str) -> ActivityAnalysisTemplate | None:
    if not code:
        return None
    db = SessionLocal()
    try:
        return get_template_by_code(db, code)
    finally:
        db.close()


def _skill_usage_refs(match_result: dict[str, Any]) -> list[Any]:
    skill_details = match_result.get("skill_details")
    if isinstance(skill_details, list) and skill_details:
        return skill_details

    dependent_components = match_result.get("dependent_components")
    if isinstance(dependent_components, list) and dependent_components:
        return dependent_components

    skill_sequence = match_result.get("skill_sequence")
    return skill_sequence if isinstance(skill_sequence, list) else []


def _is_uploaded_file_report_context(state: AgentState) -> bool:
    return bool(
        state.get("uploaded_activity_dataset")
        or state.get("workflow_key") == "uploaded_activity_report"
    )


def _filter_templates_for_context(
    templates: list[dict[str, Any]],
    state: AgentState,
    activities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    perspective_key = str(state.get("perspective_key") or "")
    if perspective_key:
        return _filter_templates_by_perspective(templates, state, perspective_key)

    outbound_context = _is_outbound_report_context(state, activities)
    if outbound_context:
        return templates

    filtered = [template for template in templates if not _is_outbound_template(template)]
    removed = len(templates) - len(filtered)
    if removed:
        logger.info(
            "活动报告模板候选过 已排除外呼模count=%d reason=outbound_data_not_found_or_not_single_activity",
            removed,
        )
    return filtered


def _filter_templates_by_perspective(
    templates: list[dict[str, Any]],
    state: AgentState,
    perspective_key: str,
) -> list[dict[str, Any]]:
    """视角驱动的候选过滤（设计文档 §6.1）：任一级过滤为空则回退上一级。"""
    if perspective_key == "outbound_call_analysis":
        if state.get("workflow_mode") == "direct_outbound_report":
            preferred = [t for t in templates if _is_outbound_template(t)]
            return preferred or templates
        # 多活动混合路径：多活动分析模板优先，其中外呼类优先
        multi = [t for t in templates if _is_multi_activity_template(t)]
        candidates = multi or templates
        outbound = [t for t in candidates if _is_outbound_template(t)]
        return outbound or candidates

    keyword = str(state.get("perspective_keyword") or "")
    filtered = [t for t in templates if not _is_outbound_template(t)] or templates
    if keyword:
        preferred = [t for t in filtered if keyword in _template_match_text(t)]
        return preferred or filtered
    return filtered


def _is_outbound_report_context(state: AgentState, activities: list[dict[str, Any]]) -> bool:
    return (
        len(activities) == 1
        and bool(state.get("outbound_activity_data_found"))
        and state.get("workflow_mode") == "direct_outbound_report"
        and bool(state.get("outbound_activity_data"))
    )


def _template_match_text(template: dict[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in (
            template.get("template_name"),
            template.get("name"),
            template.get("template_desc"),
            template.get("desc"),
            template.get("description"),
            template.get("type"),
            " ".join(template.get("skill_sequence") or template.get("skills") or []),
        )
    ).lower()


def _is_outbound_template(template: dict[str, Any]) -> bool:
    return any(
        keyword in _template_match_text(template)
        for keyword in ("外呼", "电话外呼", "电话营销", "call", "outbound")
    )


def _is_multi_activity_template(template: dict[str, Any]) -> bool:
    return any(keyword in _template_match_text(template) for keyword in ("多活动", "对比"))


def _fallback_match(activities: list[dict[str, Any]], templates: list[dict[str, Any]]) -> dict[str, Any]:
    selected_text = " ".join(_activity_text(activity) for activity in activities).lower()
    best_template = max(
        templates,
        key=lambda template: _score_template(template, selected_text, len(activities)),
    )
    return {
        "template_id": best_template.get("template_id") or best_template.get("code") or "",
        "template_name": best_template.get("template_name") or best_template.get("name") or "",
        "activity_ids": [_activity_id(activity) for activity in activities],
        "skill_sequence": best_template.get("skill_sequence") or best_template.get("skills") or [],
        "dependent_components": best_template.get("dependent_components") or [],
        "reasoning": "根据当前勾选活动数量、活动名称、渠道和活动描述进行保底匹配",
    }


def _score_template(template: dict[str, Any], activity_text: str, activity_count: int) -> int:
    template_text = " ".join(
        str(value or "")
        for value in (
            template.get("template_name"),
            template.get("name"),
            template.get("template_desc"),
            template.get("desc"),
            template.get("type"),
            " ".join(template.get("skill_sequence") or template.get("skills") or []),
        )
    ).lower()
    score = 0
    if activity_count > 1 and ("多活动" in template_text or "对比" in template_text):
        score += 8
    if activity_count == 1 and any(keyword in activity_text for keyword in ("外呼", "电话", "call")):
        if any(keyword in template_text for keyword in ("外呼", "电话", "call")):
            score += 8
    for keyword in ("线上", "线下", "渠道", "客户", "客群", "roi", "资产", "存款", "缴存", "营销"):
        if keyword in activity_text and keyword in template_text:
            score += 2
    return score


def _activity_text(activity: dict[str, Any]) -> str:
    return " ".join(
        str(value or "")
        for value in (
            activity.get("name"),
            activity.get("activity_name"),
            activity.get("actName"),
            activity.get("act_name"),
            activity.get("channel"),
            activity.get("activity_type"),
            activity.get("actTypeCd"),
            activity.get("goal"),
            activity.get("target"),
            activity.get("content"),
            activity.get("actDesc"),
            activity.get("活动名称"),
            activity.get("活动内容"),
            activity.get("活动运营目标"),
        )
    )


def _activity_id(activity: dict[str, Any]) -> str:
    return str(
        activity.get("activity_id")
        or activity.get("act_no")
        or activity.get("actNo")
        or activity.get("活动编号")
        or ""
    ).strip()
