from __future__ import annotations

import logging
import time
from datetime import date

from src.config import extract_json
from src.llm import get_model
from src.report_pipeline.period import compute_analysis_period
from src.report_pipeline.state import AgentState
from src.report_pipeline.prompts.marketing_workflow import COMPONENT_VALUE_PARAM_PROMPT
from src.services.system_prompt_service import format_runtime_prompt
from src.domain.report.template_skill import unique_ordered
from src.services.marketing_api_service import fetch_component_values

logger = logging.getLogger("njbank.agent")


async def component_value_fetch_node(state: AgentState) -> dict:
    match_result = state.get("template_match_result") or {}
    matched_data_templates = state.get("matched_data_templates") or match_result.get("matched_data_templates") or []
    intent = state.get("marketing_intent") or {}
    if not match_result and not matched_data_templates:
        return {"next_agent": "finalize", "final_response": "未完成数据模板匹配，无法获取组件数值"}

    t0 = time.monotonic()
    templates_to_fetch = matched_data_templates or [match_result]
    logger.info("组件数值获取开 matched_data_templates=%d", len(templates_to_fetch))

    request_results = []
    request_params = []
    errors = []
    activities = state.get("activity_list") or []
    for matched_template in templates_to_fetch:
        params = await _build_component_params(matched_template, intent, activities)
        request_params.append(params)
        result = fetch_component_values(params)
        if not result.success:
            errors.append(
                {
                    "template_id": matched_template.get("template_id", ""),
                    "template_name": matched_template.get("template_name", ""),
                    "error": result.error,
                }
            )
            continue

        request_results.append(
            {
                "template_id": matched_template.get("template_id", ""),
                "template_name": matched_template.get("template_name", ""),
                "similarity_score": matched_template.get("similarity_score"),
                "similarity_rank": matched_template.get("similarity_rank"),
                "params": params,
                "values": result.data or {},
            }
        )

    if not request_results:
        return {
            "next_agent": "finalize",
            "final_response": f"组件数据获取失败：{errors[0]['error'] if errors else '未知错误'}",
        }

    component_values = _combine_component_values(request_results, templates_to_fetch, errors)
    logger.info(
        "组件数值获取完 templates=%d merged_keys=%d errors=%d (%.2fs)",
        len(request_results),
        len(component_values.get("component_values") or {}),
        len(errors),
        time.monotonic() - t0,
    )
    return {
        "component_value_params": {
            "requests": request_params,
            "matched_data_templates": templates_to_fetch,
        },
        "component_values": component_values,
        "next_agent": "supervisor",
    }


async def _build_component_params(match_result: dict, intent: dict, activities: list[dict]) -> dict:
    model = get_model("data_analysis", temperature=0.1)
    response = await model.invoke(
        format_runtime_prompt(
            "component_value_param",
            COMPONENT_VALUE_PARAM_PROMPT,
            match_result=match_result,
            activities=activities,
            intent=intent,
        )
    )
    logger.debug("组件数值API参数原始响应: %s", response.content)
    logger.info("组件数值API参数原始响应长度: size=%d", len(response.content or ""))
    try:
        params = extract_json(response.content)
    except Exception as exc:
        logger.warning("组件数值API参数JSON解析失败，使用保底参 %s", str(exc))
        metrics = []
        for component in match_result.get("dependent_components", []):
            metrics.extend(component.get("metrics", []))
        params = {
            "template_id": match_result.get("template_id", ""),
            "activity_ids": match_result.get("activity_ids", []),
            "component_ids": match_result.get("component_ids", []),
            "metrics": sorted(set(metrics)),
        }

    ordered_component_ids = unique_ordered(
        component.get("component_id") for component in match_result.get("dependent_components", [])
    ) or unique_ordered(match_result.get("component_ids", []))
    if ordered_component_ids:
        params["component_ids"] = ordered_component_ids
    if match_result.get("template_id"):
        params["template_id"] = match_result.get("template_id")
    if match_result.get("activity_ids"):
        params["activity_ids"] = match_result.get("activity_ids")
    activity_period = compute_analysis_period(activities, date.today())
    if activity_period.get("start_date"):
        params["start_date"] = activity_period["start_date"]
    if activity_period.get("end_date"):
        params["end_date"] = activity_period["end_date"]
    return params


def _combine_component_values(
    request_results: list[dict],
    matched_data_templates: list[dict],
    errors: list[dict],
) -> dict:
    merged_values: dict = {}
    template_component_values: dict = {}
    for item in request_results:
        template_id = str(item.get("template_id") or item.get("template_name") or "").strip()
        values = item.get("values") or {}
        template_component_values[template_id] = {
            "template_id": item.get("template_id", ""),
            "template_name": item.get("template_name", ""),
            "similarity_score": item.get("similarity_score"),
            "similarity_rank": item.get("similarity_rank"),
            "params": item.get("params") or {},
            "values": values,
        }
        _merge_values(merged_values, template_id, values)

    payload = {
        "component_values": merged_values,
        "template_component_values": template_component_values,
        "matched_data_templates": [
            {
                "template_id": item.get("template_id", ""),
                "template_name": item.get("template_name", ""),
                "similarity_score": item.get("similarity_score"),
                "similarity_rank": item.get("similarity_rank"),
                "component_ids": item.get("component_ids", []),
                "skill_sequence": item.get("skill_sequence", []),
            }
            for item in matched_data_templates
        ],
    }
    if errors:
        payload["errors"] = errors
    return payload


def _merge_values(merged_values: dict, template_id: str, values) -> None:
    if isinstance(values, dict):
        inner_values = values.get("component_values") if isinstance(values.get("component_values"), dict) else values
        for key, value in inner_values.items():
            if key in {"matched_data_templates", "template_component_values", "errors"}:
                continue
            if key not in merged_values:
                merged_values[key] = value
            elif isinstance(merged_values[key], list) and isinstance(value, list):
                merged_values[key].extend(value)
            else:
                merged_values[f"{template_id}:{key}"] = value
        return
    if isinstance(values, list):
        merged_values[template_id] = values
        return
    merged_values[template_id] = values
