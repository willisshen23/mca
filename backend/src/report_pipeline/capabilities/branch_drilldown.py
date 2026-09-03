"""支行机构对比下钻。

某分行参与活动人数占全行 ≥95% 时，分行间对比已失去区分度，
将该模块（plate）的分行维度对比替换为该分行下属支行机构对比。
判断与替换均为确定性逻辑，不依赖 LLM。
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Iterator

from src.report_pipeline.state import AgentState

logger = logging.getLogger("activity-analysis.agent")

DRILLDOWN_THRESHOLD = 0.95

_PARTICIPATION_KEYWORD = "参与"
_PARTICIPATION_UNIT_KEYWORDS = ("人数", "客户数")
_BRANCH_KEYWORD = "分行"
_SUB_BRANCH_KEYWORD = "支行"
_FRONT_CALC_INDEX_NO = "前端运算指标"


def _iter_plates(node: Any) -> Iterator[dict]:
    """递归产出所有模块 dict（含 list 类型 plateShowIndCfgInfDtoList）。"""
    if isinstance(node, dict):
        if isinstance(node.get("plateShowIndCfgInfDtoList"), list):
            yield node
        for value in node.values():
            yield from _iter_plates(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_plates(item)


def _find_dimension(indicator: dict, keyword: str) -> dict | None:
    """在指标维度配置（cfgTypeCd=="1"）中找 indexName 含 keyword 的条目。"""
    rules = indicator.get("plateRuleCfgInfList")
    if not isinstance(rules, list):
        return None
    for entry in rules:
        if not isinstance(entry, dict) or str(entry.get("cfgTypeCd")) != "1":
            continue
        if keyword in str(entry.get("indexName") or ""):
            return entry
    return None


def _metric_key(indicator: dict) -> str:
    """指标匹配键：普通指标用 indexNo；前端运算指标用计算公式。"""
    index_no = str(indicator.get("indexNo") or "")
    if index_no and index_no != _FRONT_CALC_INDEX_NO:
        return index_no
    rules = indicator.get("plateRuleCfgInfList")
    if isinstance(rules, list):
        for entry in rules:
            if isinstance(entry, dict) and str(entry.get("cfgTypeCd")) == "2":
                content = str(entry.get("cfgContent") or "").strip()
                if content:
                    return f"formula:{content}"
    return index_no


def _is_participation_indicator(indicator: dict) -> bool:
    """参与人数口径：名称含「参与」且含「人数/客户数」（indexName 优先，indexShowName 兜底）。"""
    names = [str(indicator.get("indexName") or ""), str(indicator.get("indexShowName") or "")]
    return any(
        _PARTICIPATION_KEYWORD in name and any(unit in name for unit in _PARTICIPATION_UNIT_KEYWORDS)
        for name in names
    )


def _dominant_branch(indicator: dict, branch_index_no: str) -> tuple[str, float] | None:
    """按分行汇总 totalCount（跨其他维度），返回（主导分行, 占比）；无有效数据返回 None。"""
    rows = indicator.get("resData")
    if not isinstance(rows, list) or not branch_index_no:
        return None
    totals: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        branch = str(row.get(branch_index_no) or "").strip()
        if not branch:
            continue
        try:
            count = float(row.get("totalCount") or 0)
        except (TypeError, ValueError):
            continue
        totals[branch] = totals.get(branch, 0.0) + count
    total = sum(totals.values())
    if total <= 0:
        return None
    branch, value = max(totals.items(), key=lambda item: item[1])
    return branch, value / total


def _filter_branch_rows(rows: Any, branch_index_no: str, branch_name: str) -> list[dict]:
    """取主导分行的数据行并剥离分行键。"""
    if not isinstance(rows, list):
        return []
    return [
        {key: value for key, value in row.items() if key != branch_index_no}
        for row in rows
        if isinstance(row, dict) and str(row.get(branch_index_no) or "").strip() == branch_name
    ]


def _find_subbranch_counterpart(
    indicator: dict,
    candidates: list[dict],
    branch_index_no: str,
    branch_name: str,
    consumed: set[int],
) -> dict | None:
    """找同指标、带支行维度、且含主导分行数据行的支行对照指标。"""
    key = _metric_key(indicator)
    for candidate in candidates:
        if id(candidate) in consumed or _metric_key(candidate) != key:
            continue
        if _filter_branch_rows(candidate.get("resData"), branch_index_no, branch_name):
            return candidate
    return None


def _replace_with_subbranch(indicator: dict, counterpart: dict, branch_index_no: str, branch_name: str) -> None:
    """把指标的分行维度配置与数据替换为主导分行下属支行口径。"""
    sub_dim = _find_dimension(counterpart, _SUB_BRANCH_KEYWORD)
    rules = indicator.get("plateRuleCfgInfList")
    if isinstance(rules, list):
        for index, entry in enumerate(rules):
            if (
                isinstance(entry, dict)
                and str(entry.get("cfgTypeCd")) == "1"
                and _BRANCH_KEYWORD in str(entry.get("indexName") or "")
            ):
                rules[index] = copy.deepcopy(sub_dim)
    indicator["resData"] = _filter_branch_rows(counterpart.get("resData"), branch_index_no, branch_name)


def _remove_consumed(node: Any, consumed: set[int]) -> None:
    """原地移除被消费的支行对照指标；空模块一并移除。列表一律切片赋值（共享引用）。"""
    if isinstance(node, dict):
        for value in node.values():
            _remove_consumed(value, consumed)
        indicators = node.get("plateShowIndCfgInfDtoList")
        if isinstance(indicators, list):
            indicators[:] = [item for item in indicators if id(item) not in consumed]
        for value in node.values():
            if isinstance(value, list):
                value[:] = [
                    item
                    for item in value
                    if not (
                        isinstance(item, dict)
                        and isinstance(item.get("plateShowIndCfgInfDtoList"), list)
                        and not item["plateShowIndCfgInfDtoList"]
                    )
                ]
    elif isinstance(node, list):
        for item in node:
            _remove_consumed(item, consumed)


def apply_branch_drilldown(component_values: Any) -> dict:
    """对 component_values 原地执行支行下钻，返回触发/跳过明细。"""
    plates = list(_iter_plates(component_values))
    subbranch_indicators = [
        indicator
        for plate in plates
        for indicator in plate["plateShowIndCfgInfDtoList"]
        if isinstance(indicator, dict) and _find_dimension(indicator, _SUB_BRANCH_KEYWORD)
    ]

    triggered: list[dict] = []
    skipped: list[dict] = []
    consumed: set[int] = set()

    for plate in plates:
        plate_name = str(plate.get("plateName") or "")
        indicators = [
            indicator
            for indicator in plate["plateShowIndCfgInfDtoList"]
            if isinstance(indicator, dict)
        ]
        # 分行组：有分行维度且不带支行维度（带支行维度的是对照组）
        branch_group = [
            indicator
            for indicator in indicators
            if _find_dimension(indicator, _BRANCH_KEYWORD)
            and not _find_dimension(indicator, _SUB_BRANCH_KEYWORD)
        ]
        if not branch_group:
            continue

        participation = next((i for i in branch_group if _is_participation_indicator(i)), None)
        if participation is None:
            skipped.append({"plate": plate_name, "reason": "no_participation_indicator"})
            continue

        branch_dim = _find_dimension(participation, _BRANCH_KEYWORD) or {}
        branch_index_no = str(branch_dim.get("indexNo") or "")
        dominant = _dominant_branch(participation, branch_index_no)
        if dominant is None:
            skipped.append({"plate": plate_name, "reason": "empty_or_zero_participation"})
            continue
        branch_name, share = dominant
        if share < DRILLDOWN_THRESHOLD:
            continue

        # 全有或全无：分行组每个指标都要找到可过滤的支行对照指标
        counterparts: dict[int, dict] = {}
        for indicator in branch_group:
            match = _find_subbranch_counterpart(
                indicator, subbranch_indicators, branch_index_no, branch_name, consumed
            )
            if match is None:
                counterparts = {}
                break
            counterparts[id(indicator)] = match
        if not counterparts:
            logger.warning(
                "branch_drilldown 触发条件满足但支行数据缺失: plate=%s branch=%s share=%.4f",
                plate_name, branch_name, share,
            )
            skipped.append({
                "plate": plate_name,
                "reason": "missing_subbranch_data",
                "dominant_branch": branch_name,
                "share": round(share, 4),
            })
            continue

        for indicator in branch_group:
            counterpart = counterparts[id(indicator)]
            _replace_with_subbranch(indicator, counterpart, branch_index_no, branch_name)
            consumed.add(id(counterpart))
        plate["branchDrilldownNote"] = (
            f"{branch_name}参与活动人数占全行{share:.1%}（≥95%），"
            f"本模块原分行对比已替换为{branch_name}下属支行机构对比。"
        )
        logger.info(
            "branch_drilldown 触发: plate=%s branch=%s share=%.4f metrics=%d",
            plate_name, branch_name, share, len(branch_group),
        )
        triggered.append({"plate": plate_name, "dominant_branch": branch_name, "share": round(share, 4)})

    if consumed:
        _remove_consumed(component_values, consumed)
    return {"triggered": triggered, "skipped": skipped}


async def branch_drilldown_node(state: AgentState) -> dict:
    """报告管线节点：支行机构对比下钻。绝不中断管线。"""
    component_values = state.get("component_values") or {}
    try:
        result = apply_branch_drilldown(component_values)
    except Exception:
        logger.warning("branch_drilldown 执行异常，按未触发处理", exc_info=True)
        result = {"triggered": [], "skipped": [{"plate": None, "reason": "internal_error"}]}
    return {
        "component_values": component_values,
        "branch_drilldown_result": result,
        "next_agent": "supervisor",
    }
