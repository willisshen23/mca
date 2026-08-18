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


"""branch_drilldown_node 入口测试（接前文 fixtures）。"""
from src.report_pipeline.capabilities import branch_drilldown as bd


async def test_node_returns_result_and_keeps_supervisor():
    cv = _drilldown_component_values()
    update = await bd.branch_drilldown_node({"component_values": cv})
    assert update["next_agent"] == "supervisor"
    assert len(update["branch_drilldown_result"]["triggered"]) == 1
    assert update["component_values"] is cv


async def test_node_noop_on_empty_component_values():
    update = await bd.branch_drilldown_node({"component_values": {}})
    assert update["next_agent"] == "supervisor"
    assert update["branch_drilldown_result"] == {"triggered": [], "skipped": []}


async def test_node_swallows_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        bd, "apply_branch_drilldown", lambda cv: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    update = await bd.branch_drilldown_node({"component_values": {"component_values": {"T1": []}}})
    assert update["next_agent"] == "supervisor"
    assert update["branch_drilldown_result"]["triggered"] == []
