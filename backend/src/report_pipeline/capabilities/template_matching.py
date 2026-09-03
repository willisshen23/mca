from __future__ import annotations

import logging
import re
import time
from typing import Any

from src.config import extract_json, get_settings
from src.llm import get_model
from src.report_pipeline.state import AgentState
from src.report_pipeline.prompts.marketing_workflow import TEMPLATE_MATCHING_PROMPT
from src.services.system_prompt_service import format_runtime_prompt
from src.domain.report.template_skill import apply_template_skill_order, unique_ordered

logger = logging.getLogger("activity-analysis.agent")


async def template_matching_node(state: AgentState) -> dict:
    activities = state.get("activity_list") or []
    templates = state.get("template_list") or []
    intent = state.get("marketing_intent") or {}

    if not activities:
        return {"next_agent": "finalize", "final_response": "未获取到活动列表，无法匹配分析数据模板"}
    if not templates:
        return {"next_agent": "finalize", "final_response": "未获取到数据模板列表，无法匹配分析数据模板"}

    t0 = time.monotonic()
    logger.info("Agent1数据模板匹配开")
    model = get_model("report_generation")
    response = await model.invoke(
        format_runtime_prompt(
            "template_matching",
            TEMPLATE_MATCHING_PROMPT,
            user_text=_latest_user_text(state),
            intent=intent,
            activities=activities,
            templates=templates,
        )
    )
    logger.debug("Agent1数据模板匹配原始响应: %s", response.content)
    logger.info("Agent1数据模板匹配原始响应长度: size=%d", len(response.content or ""))

    try:
        raw_match_result = extract_json(response.content)
    except Exception as exc:
        logger.warning("Agent1数据模板匹配JSON解析失败，使用保底打分匹 %s", str(exc))
        raw_match_result = {}

    top_n = max(int(get_settings().bank_marketing_data_template_match_top_n or 1), 1)
    matched_data_templates = _rank_data_templates(
        raw_match_result, templates, activities, intent, top_n,
        perspective_keyword=str(state.get("perspective_keyword") or ""),
    )
    if not matched_data_templates:
        return {"next_agent": "finalize", "final_response": "未匹配到可用数据模板，无法继续获取组件数值"}

    match_result = {
        **matched_data_templates[0],
        "matched_data_templates": matched_data_templates,
        "match_strategy": "similarity_score_top_n",
        "top_n": top_n,
    }
    logger.info(
        "Agent1数据模板匹配完成: top_n=%d matched=%s (%.2fs)",
        top_n,
        [
            {
                "template_id": item.get("template_id"),
                "score": item.get("similarity_score"),
            }
            for item in matched_data_templates
        ],
        time.monotonic() - t0,
    )
    return {
        "template_match_result": match_result,
        "matched_data_templates": matched_data_templates,
        "next_agent": "supervisor",
    }


def _rank_data_templates(
    raw_match_result: Any,
    templates: list[dict],
    activities: list[dict],
    intent: dict,
    top_n: int,
    perspective_keyword: str = "",
) -> list[dict]:
    llm_candidates = _extract_llm_candidates(raw_match_result)
    llm_score_by_key = {
        key: score
        for candidate in llm_candidates
        for key, score in _candidate_score_keys(candidate)
    }

    scored: list[dict] = []
    for template in templates:
        base_match = {
            "template_id": template.get("template_id") or template.get("code") or template.get("id") or "",
            "template_name": template.get("template_name") or template.get("name") or "",
            "activity_ids": _activity_ids(activities),
        }
        enriched = apply_template_skill_order(base_match, templates, activities)
        key_values = [
            str(enriched.get("template_id") or "").strip(),
            str(enriched.get("template_name") or "").strip(),
        ]
        llm_score = next((llm_score_by_key.get(key) for key in key_values if key in llm_score_by_key), None)
        heuristic_score = _similarity_score(template, activities, intent)
        final_score = round(float(llm_score) if llm_score is not None else heuristic_score, 4)
        if perspective_keyword and perspective_keyword in _template_text(template):
            final_score = min(round(final_score + 0.1, 4), 1.0)
        scored.append(
            {
                **enriched,
                "similarity_score": final_score,
                "similarity_rank": 0,
                "reasoning": _match_reason(template, heuristic_score, llm_score),
            }
        )

    scored.sort(key=lambda item: item.get("similarity_score", 0), reverse=True)
    selected = scored[:top_n]
    for index, item in enumerate(selected, start=1):
        item["similarity_rank"] = index
    return selected


def _extract_llm_candidates(raw_match_result: Any) -> list[dict]:
    if isinstance(raw_match_result, list):
        return [item for item in raw_match_result if isinstance(item, dict)]
    if not isinstance(raw_match_result, dict):
        return []
    for key in ("matched_data_templates", "matched_templates", "templates", "data_templates"):
        value = raw_match_result.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [raw_match_result]


def _candidate_score_keys(candidate: dict) -> list[tuple[str, float]]:
    score = candidate.get("similarity_score", candidate.get("score", candidate.get("match_score")))
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        return []
    if numeric_score > 1:
        numeric_score = numeric_score / 100
    keys = [
        str(candidate.get("template_id") or candidate.get("projNo") or "").strip(),
        str(candidate.get("template_name") or candidate.get("projName") or candidate.get("name") or "").strip(),
    ]
    return [(key, max(0.0, min(numeric_score, 1.0))) for key in keys if key]


def _similarity_score(template: dict, activities: list[dict], intent: dict) -> float:
    query_tokens = _tokens(
        " ".join(
            [
                str(intent.get("intent_type") or ""),
                str(intent.get("activity_type") or ""),
                str(intent.get("scene") or ""),
                str(intent.get("keyword") or ""),
                *(_activity_text(activity) for activity in activities),
            ]
        )
    )
    template_tokens = _tokens(_template_text(template))
    if not query_tokens or not template_tokens:
        return 0.1
    overlap = len(query_tokens & template_tokens)
    coverage = overlap / max(len(query_tokens), 1)
    precision = overlap / max(len(template_tokens), 1)
    score = 0.15 + coverage * 0.55 + precision * 0.25

    activity_type = str(intent.get("activity_type") or "")
    if activity_type and activity_type in template.get("activity_types", []):
        score += 0.05
    if len(activities) > 1 and any(token in template_tokens for token in {"", "对比", "横向", "活动"}):
        score += 0.08
    return max(0.0, min(score, 1.0))


def _tokens(text: str) -> set[str]:
    normalized = str(text or "").lower()
    words = set(re.findall(r"[a-z0-9_]+", normalized))
    chinese_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    for chunk in chinese_chunks:
        words.add(chunk)
        words.update(chunk[index : index + 2] for index in range(max(len(chunk) - 1, 0)))
    return {word for word in words if word.strip()}


def _template_text(template: dict) -> str:
    return " ".join(
        str(value or "")
        for value in (
            template.get("template_name"),
            template.get("name"),
            template.get("template_desc"),
            template.get("description"),
            template.get("scene"),
            " ".join(template.get("activity_types") or []),
            " ".join(template.get("skill_sequence") or template.get("skills") or []),
        )
    )


def _activity_text(activity: dict) -> str:
    return " ".join(
        str(value or "")
        for value in (
            activity.get("name"),
            activity.get("activity_name"),
            activity.get("act_name"),
            activity.get("actName"),
            activity.get("activity_type"),
            activity.get("channel"),
            activity.get("goal"),
            activity.get("target_segment"),
            activity.get("actDesc"),
            activity.get("活动名称"),
            activity.get("活动运营目标"),
            activity.get("活动内容"),
        )
    )


def _activity_ids(activities: list[dict]) -> list[str]:
    return unique_ordered(
        activity.get("activity_id")
        or activity.get("act_no")
        or activity.get("actNo")
        or activity.get("活动编号")
        for activity in activities
    )


def _match_reason(template: dict, heuristic_score: float, llm_score: float | None) -> str:
    template_name = template.get("template_name") or template.get("name") or "数据模板"
    if llm_score is not None:
        return f"{template_name} 经模型语义匹配后进入候选，并结合业务相似度排序"
    return f"{template_name} 基于活动名称、业务场景、活动类型和模板技能关键词计算相似度"


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
