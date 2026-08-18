"""分析模板匹配的视角驱动过滤测试（设计文档 §6.1）。"""
from __future__ import annotations

from src.report_pipeline.capabilities.activity_template_matching import (
    _filter_templates_for_context,
)

TPL_OUTBOUND_SINGLE = {"template_id": "t1", "template_name": "外呼活动分析模板", "template_desc": "单活动外呼"}
TPL_OUTBOUND_MULTI = {"template_id": "t2", "template_name": "多活动外呼对比模板", "template_desc": "多活动对比"}
TPL_MULTI = {"template_id": "t3", "template_name": "多活动对比分析模板", "template_desc": "多活动横向对比"}
TPL_SMS = {"template_id": "t4", "template_name": "短信活动分析模板", "template_desc": "短信"}
TPL_GENERIC = {"template_id": "t5", "template_name": "活动运营分析模板", "template_desc": "通用"}
ALL = [TPL_OUTBOUND_SINGLE, TPL_OUTBOUND_MULTI, TPL_MULTI, TPL_SMS, TPL_GENERIC]


def _ids(templates):
    return [t["template_id"] for t in templates]


def test_no_perspective_excludes_outbound_templates():
    result = _filter_templates_for_context(ALL, {}, [{"activity_id": "a1"}])
    assert "t1" not in _ids(result) and "t2" not in _ids(result)
    assert set(_ids(result)) == {"t3", "t4", "t5"}


def test_outbound_single_direct_prefers_outbound_template():
    state = {"perspective_key": "outbound_call_analysis", "workflow_mode": "direct_outbound_report"}
    result = _filter_templates_for_context(ALL, state, [{"activity_id": "a1"}])
    assert set(_ids(result)) == {"t1", "t2"}


def test_outbound_multi_prefers_multi_then_outbound():
    state = {
        "perspective_key": "outbound_call_analysis",
        "workflow_mode": "template_component_report",
        "outbound_activity_data_map": {"a1": {"x": 1}},
    }
    result = _filter_templates_for_context(ALL, state, [{"activity_id": "a1"}, {"activity_id": "a2"}])
    assert _ids(result) == ["t2"], "多活动类模板中优先外呼关键词"


def test_outbound_multi_falls_back_to_plain_multi_when_no_outbound_multi():
    templates = [TPL_OUTBOUND_SINGLE, TPL_MULTI, TPL_GENERIC]
    state = {"perspective_key": "outbound_call_analysis", "workflow_mode": "template_component_report"}
    result = _filter_templates_for_context(templates, state, [{"a": 1}, {"a": 2}])
    assert _ids(result) == ["t3"], "无多活动外呼模板时回退到多活动类（不外呼关键词）"


def test_outbound_multi_falls_back_to_all_when_no_multi_template():
    templates = [TPL_OUTBOUND_SINGLE, TPL_GENERIC]
    state = {"perspective_key": "outbound_call_analysis", "workflow_mode": "template_component_report"}
    result = _filter_templates_for_context(templates, state, [{"a": 1}, {"a": 2}])
    assert set(_ids(result)) == {"t1"}, "无多活动模板时回退后仍优先外呼关键词"
    # 说明：candidates=templates（无多活动模板）→ 外呼关键词优先 → t1


def test_sms_perspective_excludes_outbound_and_prefers_keyword():
    state = {"perspective_key": "sms_analysis", "perspective_keyword": "短信"}
    result = _filter_templates_for_context(ALL, state, [{"activity_id": "a1"}])
    assert _ids(result) == ["t4"]


def test_sms_perspective_falls_back_when_keyword_misses():
    templates = [TPL_OUTBOUND_SINGLE, TPL_MULTI, TPL_GENERIC]
    state = {"perspective_key": "sms_analysis", "perspective_keyword": "短信"}
    result = _filter_templates_for_context(templates, state, [{"activity_id": "a1"}])
    assert set(_ids(result)) == {"t3", "t5"}, "关键词无命中时回退到排除外呼后的候选"


def test_legacy_outbound_context_still_keeps_all_templates():
    """旧管线（无 perspective_key）单活动外呼直连行为不变。"""
    state = {
        "workflow_mode": "direct_outbound_report",
        "outbound_activity_data_found": True,
        "outbound_activity_data": {"x": 1},
    }
    result = _filter_templates_for_context(ALL, state, [{"activity_id": "a1"}])
    assert set(_ids(result)) == {"t1", "t2", "t3", "t4", "t5"}
