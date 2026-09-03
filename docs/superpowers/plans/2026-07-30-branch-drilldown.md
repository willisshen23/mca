# 分行报告支行机构对比下钻 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 报告中某分行参与活动人数占比 ≥95% 时，把该模块的分行维度对比替换为该分行下属支行机构对比。

**Architecture:** 在报告管线 `component_value_cleanup`（及外呼数据合并）之后、`marketing_report_synthesis` 之前插入确定性节点 `branch_drilldown_node`。节点在 `component_values` 中递归定位含「所属分行」维度的模块（plate），用纯 Python 完成占比判断与数据替换；LLM 合成节点不改动，只渲染替换后的数据。

**Tech Stack:** Python 3.12、pytest、既有 report_pipeline 节点模式（`backend/src/report_pipeline/capabilities/`）。

**设计文档：** `docs/superpowers/specs/2026-07-30-branch-drilldown-design.md`（用户已批准）。

## Global Constraints

- 阈值常量 `DRILLDOWN_THRESHOLD = 0.95`，**含恰好的 95%**（`share >= DRILLDOWN_THRESHOLD`），不做可配置化。
- 参与人数指标口径：指标名含「参与」且含「人数」或「客户数」（匹配 `indexName`，兜底匹配 `indexShowName`）。
- 触发后对模块（plate）**全有或全无**：该 plate 分行组每个指标都必须找到可过滤的支行对照指标，否则整个 plate 不触发、数据原样保留。
- 节点**绝不中断管线**：任何未预期异常捕获后按"未触发"处理并记 warning 日志；返回 `next_agent: "supervisor"`。
- 不改动 LLM 合成提示词主结构；不改前端。
- 与 spec §4.3 的一处机制偏差（已在 Task 2 Step 5 同步修订 spec）：口径说明不注入 display_requirement（它派生自活动模板匹配结果，与数据无可靠映射），改为在触发的 plate dict 上写入 `branchDrilldownNote` 字段——该字段随 report_data 原样进入合成提示词，LLM 可见。
- 数据共享引用注意：`_combine_component_values` 中 `component_values["component_values"][tid]` 与 `["template_component_values"][tid]["values"]` 引用**同一个 list 对象**。所有列表过滤必须用**切片赋值**（`lst[:] = [...]`）原地修改，禁止重新绑定，否则两个视图会不一致。

## 数据结构背景（实施者必读）

模板详情接口返回 list[plate]，原样进入 `component_values`。plate 结构：

```json
{
  "plateName": "多维分析",
  "plateShowIndCfgInfDtoList": [
    {
      "indexName": "参与活动人数", "indexNo": "I200300", "indexShowName": "参与活动人数",
      "isForeEndCalc": "0", "showFlag": "1",
      "plateRuleCfgInfList": [
        {"cfgTypeCd": "2", "cfgTypeName": "参与活动人数"},
        {"indexName": "所属分行名称", "indexNo": "I200174", "cfgTypeCd": "1",
         "especChartIndRuleCfgInfs": [{"segName": "南京分行", "segStart": "200", "segEnd": "200", "segSort": 1}]},
        {"indexName": "性别代码", "indexNo": "I200176", "cfgTypeCd": "1"}
      ],
      "resData": [{"I200174": "南京分行", "I200176": "男", "totalCount": 960}]
    }
  ]
}
```

- 维度条目：`plateRuleCfgInfList` 内 `cfgTypeCd == "1"`；分行维度 indexName 含「分行」，支行维度含「支行」。
- 数据行 `resData` 按维度 indexNo 键控，指标值为 `totalCount`；同一分行可能有多行（被性别等其他维度拆分），判断时需按分行汇总。
- 支行对照指标：与分行组指标同指标（同 `indexNo`；前端运算指标按 `cfgTypeCd=="2"` 条目的 `cfgContent` 公式匹配），维度为 [分行, 支行(, 其他)]，resData 行同时携带分行键（用于过滤主导分行）与支行键。
- 前端运算指标的 `indexNo` 是字符串 `"前端运算指标"`，不能用于匹配，必须用公式。

---

### Task 1: branch_drilldown 模块——判定逻辑（参与人数匹配 + 主导分行计算）

**Files:**
- Create: `backend/src/report_pipeline/capabilities/branch_drilldown.py`
- Test: `backend/tests/test_branch_drilldown.py`

**Interfaces:**
- Produces（Task 2/3 依赖）：
  - `DRILLDOWN_THRESHOLD: float = 0.95`
  - `_iter_plates(node: Any) -> Iterator[dict]`：递归产出所有含 list 类型 `plateShowIndCfgInfDtoList` 的 dict
  - `_find_dimension(indicator: dict, keyword: str) -> dict | None`：在 `plateRuleCfgInfList` 中找 `cfgTypeCd=="1"` 且 indexName 含 keyword 的维度条目
  - `_metric_key(indicator: dict) -> str`：指标匹配键（`indexNo`；`"前端运算指标"` 时用 `"formula:<cfgContent>"`）
  - `_is_participation_indicator(indicator: dict) -> bool`
  - `_dominant_branch(indicator: dict, branch_index_no: str) -> tuple[str, float] | None`：返回（主导分行名, 占比）；无数据/总计为 0 返回 None

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_branch_drilldown.py`：

```python
"""branch_drilldown 判定逻辑测试：参与人数匹配、主导分行占比计算。"""
from __future__ import annotations

from src.report_pipeline.capabilities.branch_drilldown import (
    DRILLDOWN_THRESHOLD,
    _dominant_branch,
    _find_dimension,
    _is_participation_indicator,
    _iter_plates,
    _metric_key,
)


def _dim(index_name: str, index_no: str) -> dict:
    return {"indexName": index_name, "indexNo": index_no, "cfgTypeCd": "1"}


def _branch_indicator(index_name="参与活动人数", index_no="I200300", rows=None, show_name="参与活动人数"):
    return {
        "indexName": index_name,
        "indexNo": index_no,
        "indexShowName": show_name,
        "isForeEndCalc": "0",
        "showFlag": "1",
        "plateRuleCfgInfList": [
            {"cfgTypeCd": "2", "cfgTypeName": index_name},
            _dim("所属分行名称", "I200174"),
            _dim("性别代码", "I200176"),
        ],
        "resData": rows if rows is not None else [
            {"I200174": "南京分行", "I200176": "男", "totalCount": 960},
            {"I200174": "南京分行", "I200176": "女", "totalCount": 200},
            {"I200174": "上海分行", "I200176": "男", "totalCount": 40},
        ],
    }


def _plate(indicators, name="多维分析"):
    return {"plateName": name, "plateNo": "MD001", "plateShowIndCfgInfDtoList": indicators}


def _component_values(plates):
    return {"component_values": {"T1": plates}}


# ---------- _iter_plates ----------

def test_iter_plates_finds_nested_plates():
    cv = _component_values([_plate([_branch_indicator()])])
    plates = list(_iter_plates(cv))
    assert len(plates) == 1
    assert plates[0]["plateName"] == "多维分析"


def test_iter_plates_ignores_non_plate_structures():
    assert list(_iter_plates({"a": [1, 2, {"b": "c"}]})) == []
    assert list(_iter_plates({"plateShowIndCfgInfDtoList": "not-a-list"})) == []


# ---------- _find_dimension ----------

def test_find_dimension_branch_and_subbranch():
    indicator = _branch_indicator()
    assert _find_dimension(indicator, "分行")["indexNo"] == "I200174"
    assert _find_dimension(indicator, "支行") is None


def test_find_dimension_ignores_metric_entries():
    indicator = _branch_indicator()
    # cfgTypeCd=="2" 的指标条目即使名字含"分行"也不算维度
    indicator["plateRuleCfgInfList"].append({"cfgTypeCd": "2", "cfgTypeName": "分行数"})
    assert _find_dimension(indicator, "分行")["indexNo"] == "I200174"


# ---------- _metric_key ----------

def test_metric_key_uses_index_no():
    assert _metric_key(_branch_indicator()) == "I200300"


def test_metric_key_front_calc_uses_formula():
    indicator = {
        "indexName": "前端运算指标",
        "indexNo": "前端运算指标",
        "plateRuleCfgInfList": [{"cfgTypeCd": "2", "cfgContent": "$I1000030$/$I2000011"}],
    }
    assert _metric_key(indicator) == "formula:$I1000030$/$I2000011"


# ---------- _is_participation_indicator ----------

def test_participation_match_by_index_name():
    assert _is_participation_indicator(_branch_indicator(index_name="参与活动人数")) is True
    assert _is_participation_indicator(_branch_indicator(index_name="参与客户数")) is True


def test_participation_match_fallback_to_show_name():
    assert _is_participation_indicator(
        _branch_indicator(index_name="客户编号", show_name="活动参与人数")
    ) is True


def test_participation_rejects_non_participation():
    assert _is_participation_indicator(_branch_indicator(index_name="AUM时点值", show_name="AUM时点值1")) is False
    assert _is_participation_indicator(_branch_indicator(index_name="活动参与率", show_name="活动参与率")) is False


# ---------- _dominant_branch ----------

def test_dominant_branch_sums_across_other_dimensions():
    indicator = _branch_indicator()
    branch, share = _dominant_branch(indicator, "I200174")
    assert branch == "南京分行"
    assert abs(share - 1160 / 1200) < 1e-9
    assert share >= DRILLDOWN_THRESHOLD


def test_dominant_branch_below_threshold():
    rows = [
        {"I200174": "南京分行", "totalCount": 60},
        {"I200174": "上海分行", "totalCount": 40},
    ]
    branch, share = _dominant_branch(_branch_indicator(rows=rows), "I200174")
    assert branch == "南京分行"
    assert share < DRILLDOWN_THRESHOLD


def test_dominant_branch_returns_none_on_zero_total():
    rows = [{"I200174": "南京分行", "totalCount": 0}]
    assert _dominant_branch(_branch_indicator(rows=rows), "I200174") is None


def test_dominant_branch_skips_bad_rows():
    rows = [
        {"I200174": "", "totalCount": 999},          # 无分行名，跳过
        {"I200174": "南京分行", "totalCount": "abc"}, # 非数值，跳过
        {"I200174": "南京分行", "totalCount": 100},
    ]
    branch, share = _dominant_branch(_branch_indicator(rows=rows), "I200174")
    assert branch == "南京分行"
    assert share == 1.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/test_branch_drilldown.py -v`
Expected: FAIL（`ModuleNotFoundError: src.report_pipeline.capabilities.branch_drilldown`）

- [ ] **Step 3: 实现模块判定部分**

创建 `backend/src/report_pipeline/capabilities/branch_drilldown.py`：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/test_branch_drilldown.py -v`
Expected: PASS（13 例）

- [ ] **Step 5: Commit**

```bash
git add backend/src/report_pipeline/capabilities/branch_drilldown.py backend/tests/test_branch_drilldown.py
git commit -m "feat: branch_drilldown 判定逻辑（参与人数匹配+主导分行占比）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 替换逻辑——`apply_branch_drilldown`（全有或全无 + 口径说明）

**Files:**
- Modify: `backend/src/report_pipeline/capabilities/branch_drilldown.py`
- Test: `backend/tests/test_branch_drilldown.py`
- Docs: `docs/superpowers/specs/2026-07-30-branch-drilldown-design.md`（§4.3 机制修订）

**Interfaces:**
- Consumes: Task 1 的全部 helper。
- Produces（Task 3 依赖）：
  - `apply_branch_drilldown(component_values: Any) -> dict`：**原地修改** component_values，返回 `{"triggered": [{"plate": str, "dominant_branch": str, "share": float}], "skipped": [{"plate": str|None, "reason": str, ...}]}`。
  - 触发后的 plate 带 `branchDrilldownNote: str` 字段。
  - 内部函数：`_filter_branch_rows(rows, branch_index_no, branch_name) -> list[dict]`、`_find_subbranch_counterpart(indicator, candidates, branch_index_no, branch_name, consumed) -> dict | None`、`_replace_with_subbranch(indicator, counterpart, branch_index_no, branch_name) -> None`、`_remove_consumed(node, consumed: set[int]) -> None`。

- [ ] **Step 1: 写失败测试（追加到 `backend/tests/test_branch_drilldown.py`）**

```python
"""apply_branch_drilldown 替换逻辑测试（接 Task 1  fixtures）。"""
import copy

from src.report_pipeline.capabilities.branch_drilldown import apply_branch_drilldown


def _subbranch_indicator(index_name="参与活动人数", index_no="I200300", rows=None, show_name="参与活动人数"):
    """支行对照指标：维度为 [分行, 支行]，数据行同时携带分行键与支行键。"""
    return {
        "indexName": index_name,
        "indexNo": index_no,
        "indexShowName": show_name,
        "isForeEndCalc": "0",
        "showFlag": "1",
        "plateRuleCfgInfList": [
            {"cfgTypeCd": "2", "cfgTypeName": index_name},
            _dim("所属分行名称", "I200174"),
            _dim("所属支行名称", "I200175"),
        ],
        "resData": rows if rows is not None else [
            {"I200174": "南京分行", "I200175": "南京城北支行", "totalCount": 620},
            {"I200174": "南京分行", "I200175": "南京城南支行", "totalCount": 540},
            {"I200174": "上海分行", "I200175": "上海浦东支行", "totalCount": 40},
        ],
    }


def _drilldown_component_values(branch_rows=None, with_subbranch=True, extra_branch_indicators=None,
                                extra_subbranch_indicators=None):
    branch_indicators = [_branch_indicator(rows=branch_rows)] + (extra_branch_indicators or [])
    subbranch_indicators = ([_subbranch_indicator()] + (extra_subbranch_indicators or [])) if with_subbranch else []
    plates = [_plate(branch_indicators + subbranch_indicators)]
    return _component_values(plates)


# ---------- 触发与替换 ----------

def test_trigger_replaces_branch_dimension_with_subbranch():
    cv = _drilldown_component_values()
    result = apply_branch_drilldown(cv)

    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["dominant_branch"] == "南京分行"

    plate = cv["component_values"]["T1"][0]
    indicators = plate["plateShowIndCfgInfDtoList"]
    # 支行对照指标被消费移除，只剩原分行组指标
    assert len(indicators) == 1
    indicator = indicators[0]
    # 维度配置：分行 → 支行
    assert _find_dimension(indicator, "分行") is None
    assert _find_dimension(indicator, "支行")["indexNo"] == "I200175"
    # 数据行：仅主导分行下属支行，且不再携带分行键
    assert indicator["resData"] == [
        {"I200175": "南京城北支行", "totalCount": 620},
        {"I200175": "南京城南支行", "totalCount": 540},
    ]
    # 口径说明
    assert "南京分行" in plate["branchDrilldownNote"]
    assert "支行机构对比" in plate["branchDrilldownNote"]


def test_trigger_at_exactly_95_percent():
    rows = [
        {"I200174": "南京分行", "totalCount": 95},
        {"I200174": "上海分行", "totalCount": 5},
    ]
    cv = _drilldown_component_values(branch_rows=rows)
    result = apply_branch_drilldown(cv)
    assert len(result["triggered"]) == 1


def test_no_trigger_below_threshold_keeps_data_unchanged():
    rows = [
        {"I200174": "南京分行", "totalCount": 60},
        {"I200174": "上海分行", "totalCount": 40},
    ]
    cv = _drilldown_component_values(branch_rows=rows)
    snapshot = copy.deepcopy(cv)
    result = apply_branch_drilldown(cv)
    assert result["triggered"] == []
    assert cv == snapshot


def test_no_trigger_when_subbranch_data_missing():
    cv = _drilldown_component_values(with_subbranch=False)
    snapshot = copy.deepcopy(cv)
    result = apply_branch_drilldown(cv)
    assert result["triggered"] == []
    assert any(s["reason"] == "missing_subbranch_data" for s in result["skipped"])
    assert cv == snapshot


def test_no_trigger_without_participation_indicator():
    cv = _component_values([_plate([_branch_indicator(index_name="AUM时点值", show_name="AUM时点值1")])])
    result = apply_branch_drilldown(cv)
    assert result["triggered"] == []
    assert any(s["reason"] == "no_participation_indicator" for s in result["skipped"])


def test_no_trigger_on_zero_total():
    cv = _drilldown_component_values(branch_rows=[{"I200174": "南京分行", "totalCount": 0}])
    result = apply_branch_drilldown(cv)
    assert result["triggered"] == []
    assert any(s["reason"] == "empty_or_zero_participation" for s in result["skipped"])


def test_multi_metric_plate_switches_all_indicators():
    extra_branch = _branch_indicator(index_name="AUM时点值", index_no="I200013", show_name="AUM时点值1")
    extra_sub = _subbranch_indicator(index_name="AUM时点值", index_no="I200013", show_name="AUM时点值1")
    cv = _drilldown_component_values(
        extra_branch_indicators=[extra_branch],
        extra_subbranch_indicators=[extra_sub],
    )
    result = apply_branch_drilldown(cv)
    assert len(result["triggered"]) == 1
    indicators = cv["component_values"]["T1"][0]["plateShowIndCfgInfDtoList"]
    assert len(indicators) == 2
    for indicator in indicators:
        assert _find_dimension(indicator, "分行") is None
        assert _find_dimension(indicator, "支行") is not None
        assert all("I200174" not in row for row in indicator["resData"])


def test_all_or_nothing_when_one_metric_lacks_counterpart():
    extra_branch = _branch_indicator(index_name="AUM时点值", index_no="I200013", show_name="AUM时点值1")
    cv = _drilldown_component_values(extra_branch_indicators=[extra_branch])  # 无对应支行指标
    snapshot = copy.deepcopy(cv)
    result = apply_branch_drilldown(cv)
    assert result["triggered"] == []
    assert any(s["reason"] == "missing_subbranch_data" for s in result["skipped"])
    assert cv == snapshot


def test_plates_are_independent():
    triggered_plate = _plate([_branch_indicator(), _subbranch_indicator()], name="模块A")
    calm_plate = _plate(
        [_branch_indicator(rows=[{"I200174": "南京分行", "totalCount": 50},
                                 {"I200174": "上海分行", "totalCount": 50}])],
        name="模块B",
    )
    cv = _component_values([triggered_plate, calm_plate])
    result = apply_branch_drilldown(cv)
    assert [t["plate"] for t in result["triggered"]] == ["模块A"]
    plate_b = cv["component_values"]["T1"][1]
    assert _find_dimension(plate_b["plateShowIndCfgInfDtoList"][0], "分行") is not None
    assert "branchDrilldownNote" not in plate_b
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/test_branch_drilldown.py -v`
Expected: 新用例 FAIL（`ImportError: cannot import name 'apply_branch_drilldown'`）

- [ ] **Step 3: 实现替换逻辑**

在 `backend/src/report_pipeline/capabilities/branch_drilldown.py` 末尾追加：

```python
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
```

注意模块顶部已有 `import copy`（Task 1 已写）；若遗漏需补上。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/test_branch_drilldown.py -v`
Expected: PASS（22 例）

- [ ] **Step 5: 同步修订 spec §4.3 机制说明**

编辑 `docs/superpowers/specs/2026-07-30-branch-drilldown-design.md`，把 §4.3 第 3 条：

> 3. 在 display_requirement 注入一句说明：「XX分行参与活动人数占比超过95%，本章原分行对比替换为该分行下属支行机构对比」，使报告读者知道口径变化；

改为：

> 3. 在触发的模块（plate）dict 上写入 `branchDrilldownNote` 字段：「XX分行参与活动人数占全行XX%（≥95%），本模块原分行对比已替换为XX分行下属支行机构对比。」该字段随 report_data 原样进入合成提示词，LLM 可见，使报告读者知道口径变化（不注入 display_requirement——它派生自活动模板匹配结果，与数据模块无可靠映射）；

- [ ] **Step 6: Commit**

```bash
git add backend/src/report_pipeline/capabilities/branch_drilldown.py backend/tests/test_branch_drilldown.py docs/superpowers/specs/2026-07-30-branch-drilldown-design.md
git commit -m "feat: branch_drilldown 替换逻辑（全有或全无+口径说明）

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 节点入口 + 管线接线 + AgentState

**Files:**
- Modify: `backend/src/report_pipeline/capabilities/branch_drilldown.py`（追加 node）
- Modify: `backend/src/report_pipeline/__init__.py`
- Modify: `backend/src/report_pipeline/state.py:76` 附近
- Modify: `backend/src/agent_v2/tools/report_gen.py:26-28`（import）与 `:436-443`（插 step）
- Test: `backend/tests/test_branch_drilldown.py`（追加 node 用例）
- Test: `backend/tests/agent_v2/test_generate_report_pipeline.py`（更新调用顺序）

**Interfaces:**
- Consumes: `apply_branch_drilldown(component_values) -> dict`（Task 2）。
- Produces:
  - `branch_drilldown_node(state: AgentState) -> dict`，返回 `{"component_values": dict, "branch_drilldown_result": {"triggered": list, "skipped": list}, "next_agent": "supervisor"}`。
  - AgentState 新键 `branch_drilldown_result: dict`。
  - 管线步骤名 `"branch_drilldown"`（出现在 `component_value_cleanup` 之后、`activity_template_matching` 之前；`direct_outbound_report` 模式不执行）。

- [ ] **Step 1: 写失败测试（追加到 `backend/tests/test_branch_drilldown.py`）**

```python
"""branch_drilldown_node 入口测试（接前文 fixtures）。"""
from src.report_pipeline.capabilities import branch_drilldown as bd


def test_node_returns_result_and_keeps_supervisor():
    cv = _drilldown_component_values()
    update = bd.branch_drilldown_node({"component_values": cv})
    assert update["next_agent"] == "supervisor"
    assert len(update["branch_drilldown_result"]["triggered"]) == 1
    assert update["component_values"] is cv


def test_node_noop_on_empty_component_values():
    update = bd.branch_drilldown_node({"component_values": {}})
    assert update["next_agent"] == "supervisor"
    assert update["branch_drilldown_result"] == {"triggered": [], "skipped": []}


def test_node_swallows_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        bd, "apply_branch_drilldown", lambda cv: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    update = bd.branch_drilldown_node({"component_values": {"component_values": {"T1": []}}})
    assert update["next_agent"] == "supervisor"
    assert update["branch_drilldown_result"]["triggered"] == []
```

并在 `backend/tests/agent_v2/test_generate_report_pipeline.py` 的 `_patch_pipeline` 中追加 mock（放在 `component_value_cleanup_node` 那行之后）：

```python
    monkeypatch.setattr(rg, "branch_drilldown_node", _make_node("branch_drilldown", calls, {"next_agent": "x"}))
```

更新两处期望顺序（`test_pipeline_call_order_multi_activity` 第 82 行附近的列表）：

```python
    assert calls == [
        "selected_activity_router",
        "template_list_fetch",
        "template_matching",
        "component_value_fetch",
        "component_value_cleanup",
        "branch_drilldown",
        "activity_template_matching",
        "marketing_report_synthesis",
    ]
```

`test_pipeline_direct_outbound_skips_template_chain`（第 119 行附近）的期望列表**不含** branch_drilldown，保持不变。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/test_branch_drilldown.py tests/agent_v2/test_generate_report_pipeline.py -v`
Expected: node 用例 FAIL（`branch_drilldown_node` 不存在）；管线顺序用例 FAIL（`rg.branch_drilldown_node` 属性不存在 / 顺序不符）

- [ ] **Step 3: 实现 node 并接线**

a) `backend/src/report_pipeline/capabilities/branch_drilldown.py` 末尾追加：

```python
def branch_drilldown_node(state: AgentState) -> dict:
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
```

b) `backend/src/report_pipeline/__init__.py`：import 区加 `from src.report_pipeline.capabilities.branch_drilldown import branch_drilldown_node`（按字母序放在 `activity_template_matching` 之后、`component_value_cleanup` 之前），`__all__` 加 `"branch_drilldown_node"`。

c) `backend/src/report_pipeline/state.py`：在 `component_value_cleanup_result: dict` 之后加一行：

```python
    branch_drilldown_result: dict
```

d) `backend/src/agent_v2/tools/report_gen.py`：
- import 区（第 26-28 行附近，与 `component_value_cleanup_node` 同组）加：

```python
from src.report_pipeline.capabilities.branch_drilldown import branch_drilldown_node
```

- 在第 436-443 行 `component_value_cleanup` step 及外呼合并块之后插入：

```python
        step("component_value_cleanup", component_value_cleanup_node)
        if s.get("outbound_activity_data_map"):
            # 合并在 cleanup 之后，避免外呼数据被空值清洗误删（设计文档 §5.3）
            s["component_values"] = _merge_outbound_into_component_values(
                s.get("component_values") or {},
                s["outbound_activity_data_map"],
            )
        step("branch_drilldown", branch_drilldown_node)
```

（即新增的 `step("branch_drilldown", ...)` 行位于外呼合并 `if` 块之后、仍在 `if s.get("workflow_mode") != "direct_outbound_report":` 块内。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/test_branch_drilldown.py tests/agent_v2/test_generate_report_pipeline.py -v`
Expected: PASS

再跑全量回归：

Run: `cd backend && venv/bin/python -m pytest tests -x -q`
Expected: 全绿（基线 77 例 + 新增约 12 例）

- [ ] **Step 5: Commit**

```bash
git add backend/src/report_pipeline/capabilities/branch_drilldown.py backend/src/report_pipeline/__init__.py backend/src/report_pipeline/state.py backend/src/agent_v2/tools/report_gen.py backend/tests/test_branch_drilldown.py backend/tests/agent_v2/test_generate_report_pipeline.py
git commit -m "feat: branch_drilldown 接入报告管线

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: mock 样本补支行数据 + 端到端人工验证

**Files:**
- Modify: `mock/通过分析模板 id 、活动 id、时间范围获取分析模板详情及活动数据api/通过分析模板 id 、活动 id、时间范围获取分析模板详情及活动数据api-返回报文结构`

**Interfaces:**
- Consumes: Task 1-3 全部。
- Produces: 可供人工端到端验证的 mock 数据——mock 的「多维分析」模块满足触发条件。

**背景：** mock 样本当前「多维分析」模块只有 `AUM时点值` 与 `前端运算指标` 两个分行维度指标，无参与人数指标、无支行维度，下钻永远不会触发。本任务给该模块补齐：①参与人数指标（分行组，南京占比 ≥95%）；②全部三个指标的支行对照组（维度 [分行, 支行]，数据行带分行键）。全有或全无要求**每个**分行组指标都有支行对照。

- [ ] **Step 1: 修改 mock 样本文件**

在「多维分析」模块（`"plateName": "多维分析"`）的 `plateShowIndCfgInfDtoList` 中：

a) 给 `AUM时点值`（I200013）指标的 `resData` 调整为南京占比 ≥95%（原三行 24/38/12 之类的数值改为）：

```json
"resData": [
    {"I200174": "南京分行", "I200176": "男", "totalCount": 1140},
    {"I200174": "上海分行", "I200176": "男", "totalCount": 24},
    {"I200174": "北京分行", "I200176": "女", "totalCount": 36}
]
```

b) 新增参与人数指标（分行组，紧随 AUM时点值 指标之后）：

```json
{
    "indSortNo": 2,
    "indSeqNo": 3,
    "indexName": "参与活动人数",
    "indexNo": "I200300",
    "indexShowName": "参与活动人数",
    "isForeEndCalc": "0",
    "plateRuleCfgInfList": [
        {"cfgTypeCd": "2", "cfgTypeName": "参与活动人数", "srcTableName": "COAP_DATA.COAP_CUST_BIZ_VAL_ANALY"},
        {
            "indexName": "所属分行名称", "indexNo": "I200174", "cfgTypeCd": "1",
            "especChartIndRuleCfgInfs": [
                {"indexNo": "I200174", "segEnd": "200", "segName": "南京分行", "segSort": 1, "segStart": "200"},
                {"indexNo": "I200174", "segEnd": "206", "segName": "上海分行", "segSort": 2, "segStart": "206"},
                {"indexNo": "I200174", "segEnd": "215", "segName": "北京分行", "segSort": 3, "segStart": "215"}
            ],
            "orderNum": "1"
        },
        {"indexName": "性别代码", "indexNo": "I200176", "cfgTypeCd": "1", "orderNum": "2"}
    ],
    "plateTypeCd": "5",
    "projNo": "XMDHD202605191506594339",
    "showFlag": "1",
    "resData": [
        {"I200174": "南京分行", "I200176": "男", "totalCount": 1140},
        {"I200174": "上海分行", "I200176": "男", "totalCount": 24},
        {"I200174": "北京分行", "I200176": "女", "totalCount": 36}
    ]
}
```

（南京 1140/1200 = 95.0%，恰好压边界，可同时验证边界行为。）

c) 新增支行对照组（同一 `plateShowIndCfgInfDtoList` 内、上述指标之后），三个指标各一份，维度为 [分行, 支行]（indexNo I200175「所属支行名称」），resData 行同时携带 I200174 与 I200175：

```json
{
    "indSortNo": 10,
    "indSeqNo": 10,
    "indexName": "参与活动人数",
    "indexNo": "I200300",
    "indexShowName": "参与活动人数（支行）",
    "isForeEndCalc": "0",
    "plateRuleCfgInfList": [
        {"cfgTypeCd": "2", "cfgTypeName": "参与活动人数"},
        {"indexName": "所属分行名称", "indexNo": "I200174", "cfgTypeCd": "1", "orderNum": "1"},
        {"indexName": "所属支行名称", "indexNo": "I200175", "cfgTypeCd": "1", "orderNum": "2"}
    ],
    "plateTypeCd": "5",
    "projNo": "XMDHD202605191506594339",
    "showFlag": "1",
    "resData": [
        {"I200174": "南京分行", "I200175": "南京城北支行", "totalCount": 590},
        {"I200174": "南京分行", "I200175": "南京城南支行", "totalCount": 550},
        {"I200174": "上海分行", "I200175": "上海浦东支行", "totalCount": 24},
        {"I200174": "北京分行", "I200175": "北京中关村支行", "totalCount": 36}
    ]
},
{
    "indSortNo": 11,
    "indSeqNo": 11,
    "indexName": "AUM时点值",
    "indexNo": "I200013",
    "indexShowName": "AUM时点值（支行）",
    "isForeEndCalc": "0",
    "plateRuleCfgInfList": [
        {"cfgTypeCd": "2", "cfgTypeName": "AUM时点值"},
        {"indexName": "所属分行名称", "indexNo": "I200174", "cfgTypeCd": "1", "orderNum": "1"},
        {"indexName": "所属支行名称", "indexNo": "I200175", "cfgTypeCd": "1", "orderNum": "2"}
    ],
    "plateTypeCd": "5",
    "projNo": "XMDHD202605191506594339",
    "showFlag": "1",
    "resData": [
        {"I200174": "南京分行", "I200175": "南京城北支行", "totalCount": 590},
        {"I200174": "南京分行", "I200175": "南京城南支行", "totalCount": 550},
        {"I200174": "上海分行", "I200175": "上海浦东支行", "totalCount": 24},
        {"I200174": "北京分行", "I200175": "北京中关村支行", "totalCount": 36}
    ]
},
{
    "indSortNo": 12,
    "indSeqNo": 12,
    "indexName": "前端运算指标",
    "indexNo": "前端运算指标",
    "indexShowName": "前端运算指标（支行）",
    "isForeEndCalc": "1",
    "plateRuleCfgInfList": [
        {"cfgContent": "$I1000030$/$I2000011", "cfgTypeCd": "2", "cfgTypeName": "前端运算指标"},
        {"indexName": "所属分行名称", "indexNo": "I200174", "cfgTypeCd": "1", "orderNum": "1"},
        {"indexName": "所属支行名称", "indexNo": "I200175", "cfgTypeCd": "1", "orderNum": "2"}
    ],
    "plateTypeCd": "5",
    "projNo": "XMDHD202605191506594339",
    "showFlag": "1",
    "resData": [
        {"I200174": "南京分行", "I200175": "南京城北支行", "totalCount": 590147.5},
        {"I200174": "南京分行", "I200175": "南京城南支行", "totalCount": 550137.5},
        {"I200174": "上海分行", "I200175": "上海浦东支行", "totalCount": 24006.0},
        {"I200174": "北京分行", "I200175": "北京中关村支行", "totalCount": 36009.0}
    ]
}
```

注意：该文件是"带注释的 JSON"（`--注释` 后缀由 mock 的 `_load_json_like_rows` 剥离），新增内容不要带行尾注释以外的语法错误；保持与原文件相同的缩进风格（tab）。

同时把原 `前端运算指标`（分行组那条）的 resData 三行数值同步改为 1140/24/36 的放大值（如 `1140250.5` 等），使两个分组量级一致——精确值不限，保持演示合理即可。

- [ ] **Step 2: 验证 mock 能正常加载样本**

Run: `cd mock && python -c "from router import _build_template_detail_payload; import json; p=_build_template_detail_payload('X', [], '', ''); print(len(p)); print(json.dumps([pl.get('plateName') for pl in p], ensure_ascii=False))"`
Expected: 正常打印，无 JSON 解析异常，模块清单含「多维分析」

- [ ] **Step 3: 单元级冒烟——直接对 mock 样本跑 apply_branch_drilldown**

Run:

```bash
cd backend && venv/bin/python -c "
import sys, json
sys.path.insert(0, '../mock')
from router import _build_template_detail_payload
from src.report_pipeline.capabilities.branch_drilldown import apply_branch_drilldown
plates = _build_template_detail_payload('X', [], '', '')
cv = {'component_values': {'T1': plates}}
result = apply_branch_drilldown(cv)
print(json.dumps(result, ensure_ascii=False, indent=2))
"
```

Expected: `triggered` 含「多维分析」、dominant_branch 为「南京分行」、share 为 0.95；触发模块的指标维度已替换为支行、resData 只剩南京两行支行数据、带 `branchDrilldownNote`。

- [ ] **Step 4: 人工端到端验证**

启动 mock、后端、前端（参考 README/DEPLOY.md 的本地启动方式），在对话中选择一个活动生成分行维度的活动分析报告，确认：

1. 报告中原分行对比位置展示的是南京分行下属支行（南京城北支行/南京城南支行）的机构对比；
2. 报告中有口径说明文字（来源 `branchDrilldownNote`）；
3. 后端日志出现 `branch_drilldown 触发: plate=多维分析 branch=南京分行 share=0.9500`；
4. 报告中不出现北京/上海分行的对比数据，也不出现凭空数值。

若不触发，先查后端日志 `branch_drilldown` 相关 warning（`missing_subbranch_data` / `no_participation_indicator`）。

- [ ] **Step 5: Commit**

```bash
git add "mock/通过分析模板 id 、活动 id、时间范围获取分析模板详情及活动数据api/通过分析模板 id 、活动 id、时间范围获取分析模板详情及活动数据api-返回报文结构"
git commit -m "chore: mock 样本补充支行维度数据用于下钻端到端验证

Co-Authored-By: Claude <noreply@anthropic.com>"
```
