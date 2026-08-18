"""外呼视角探测与分流测试（设计文档 §3、§4；指向 agent_v3 impl 层）。

mock fetch_outbound_activity_data 与 run_report_pipeline，无 LLM/网络。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import report_gen as rg

ACTIVITIES = [
    {"activity_id": "act-1", "name": "外呼促活", "start_date": "2026-06-01", "end_date": "2026-06-30"},
    {"activity_id": "act-2", "name": "短信营销", "start_date": "2026-06-01", "end_date": "2026-06-30"},
    {"activity_id": "act-3", "name": "厅堂活动", "start_date": "2026-06-01", "end_date": "2026-06-30"},
]


def _ctx(queue=None):
    return ToolContext(
        state={
            "analysis_queue": queue if queue is not None else ACTIVITIES,
            "original_user_text": "用外呼视角生成报告",
        },
        request=ToolRequestContext(user_id="u1", thread_id="t-1"),
        tool_call_id="call-1",
    )


def _merged_data(found: set[str]) -> dict:
    rows = [{"act_no": key, "act_name": f"活动{key}"} for key in sorted(found)]
    return {
        "matched": bool(found),
        "matched_act_nos": sorted(found),
        "act_no": sorted(found),
        "activity_id": sorted(found),
        "totalCount": len(rows),
        "sources": {
            "EDW_RTL_MED_ACTIVITY_BASE_INFO": {"totalCount": len(rows), "result": rows},
        },
    }


def _patch_probe(monkeypatch, found_keys=(), error_keys=(), merged_error=False):
    """mock 外呼接口：act_no 为 list 走合并探测，为 str 走回退逐活动探测。"""
    calls = []

    def fake_fetch(params):
        calls.append(params)
        key = params["act_no"]
        if isinstance(key, list):
            if merged_error:
                return SimpleNamespace(success=False, data=None, error="连接超时")
            found = set(key) & set(found_keys)
            return SimpleNamespace(success=True, data=_merged_data(found), error="")
        if key in error_keys:
            return SimpleNamespace(success=False, data=None, error="连接超时")
        if key in found_keys:
            return SimpleNamespace(success=True, data={"接通率": 0.6}, error="")
        return SimpleNamespace(success=True, data={"matched": False}, error="")

    monkeypatch.setattr(rg, "fetch_outbound_activity_data", fake_fetch)
    return calls


def _patch_pipeline_capture(monkeypatch):
    seeds = []

    async def fake_pipeline(seed, writer):
        seeds.append(seed)
        return {
            "html_report": "<html><body>ok</body></html>",
            "activity_template_match_result": {"template_name": "多活动分析模板"},
            "matched_data_templates": [],
        }

    monkeypatch.setattr(rg, "run_report_pipeline", fake_pipeline)
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))
    monkeypatch.setattr(rg, "_finish_report_run", lambda *a, **k: None)
    return seeds


def _call(ctx=None, **kwargs):
    return asyncio.run(rg.generate_report(ctx if ctx is not None else _ctx(), **kwargs))


def _content_of(result) -> str:
    """成功路径返回 ToolOutcome（state_updates 落图状态），失败/确认路径返回文本。"""
    if isinstance(result, str):
        return result
    return result.content


def test_probe_params_carry_no_dates(monkeypatch):
    calls = _patch_probe(monkeypatch, found_keys={"act-1", "act-2", "act-3"})
    _patch_pipeline_capture(monkeypatch)
    _call(perspective="outbound_call_analysis", confirm_mixed=True)
    assert len(calls) == 1, "多活动应合并为一次外呼探测调用"
    params = calls[0]
    assert params["act_no"] == ["act-1", "act-2", "act-3"]
    assert "start_date" not in params and "end_date" not in params
    assert "actStartDt" not in params and "actEndDt" not in params


def test_all_non_outbound_interrupts_business(monkeypatch):
    _patch_probe(monkeypatch, found_keys=set())
    pipeline = _patch_pipeline_capture(monkeypatch)
    content = _call(perspective="outbound_call_analysis")
    assert content.startswith("ERROR:")
    assert "所选的活动均不是外呼活动，无法使用外呼渠道视角进行分析" in content
    assert pipeline == [], "业务中断不得进入管线"


def test_mixed_without_confirm_returns_need_confirm(monkeypatch):
    _patch_probe(monkeypatch, found_keys={"act-1"})
    pipeline = _patch_pipeline_capture(monkeypatch)
    content = _call(perspective="outbound_call_analysis")
    payload = json.loads(content)
    assert payload["status"] == "need_confirm"
    assert payload["non_outbound_activities"] == ["短信营销", "厅堂活动"]
    assert payload["outbound_activities"] == ["外呼促活"]
    assert "是否继续生成报告" in payload["message"]
    assert pipeline == [], "未确认不得进入管线"


def test_mixed_confirmed_enters_pipeline_with_map(monkeypatch):
    _patch_probe(monkeypatch, found_keys={"act-1"})
    seeds = _patch_pipeline_capture(monkeypatch)
    content = _content_of(_call(perspective="outbound_call_analysis", confirm_mixed=True))
    assert not content.startswith("ERROR:"), content
    assert len(seeds) == 1
    seed = seeds[0]
    assert set(seed["outbound_activity_data_map"]) == {"act-1"}
    data = seed["outbound_activity_data_map"]["act-1"]
    assert data["act_no"] == "act-1"
    for source in data["sources"].values():
        assert all(row["act_no"] == "act-1" for row in source["result"])
    assert seed["perspective_key"] == "outbound_call_analysis"
    assert seed["workflow_mode"] == "template_component_report"
    assert len(seed["activity_list"]) == 3, "数据模板取数覆盖全部活动"


def test_all_outbound_multi_activity_no_confirm_needed(monkeypatch):
    _patch_probe(monkeypatch, found_keys={"act-1", "act-2", "act-3"})
    seeds = _patch_pipeline_capture(monkeypatch)
    content = _content_of(_call(perspective="outbound_call_analysis"))
    payload = json.loads(content)
    assert payload["status"] == "ok", content
    assert seeds[0]["workflow_mode"] == "template_component_report"
    data_map = seeds[0]["outbound_activity_data_map"]
    assert len(data_map) == 3
    for key, data in data_map.items():
        assert data["act_no"] == key
        for source in data["sources"].values():
            assert all(row["act_no"] == key for row in source["result"])


def test_single_outbound_hit_direct_mode(monkeypatch):
    _patch_probe(monkeypatch, found_keys={"act-1"})
    seeds = _patch_pipeline_capture(monkeypatch)
    content = _content_of(_call(
        perspective="outbound_call_analysis",
        ctx=_ctx(queue=[ACTIVITIES[0]]),
    ))
    assert not content.startswith("ERROR:"), content
    assert seeds[0]["workflow_mode"] == "direct_outbound_report"
    assert seeds[0]["outbound_activity_data"]["act_no"] == "act-1"


def test_single_non_outbound_interrupts_business(monkeypatch):
    _patch_probe(monkeypatch, found_keys=set())
    content = _call(
        perspective="outbound_call_analysis",
        ctx=_ctx(queue=[ACTIVITIES[0]]),
    )
    assert "所选的活动均不是外呼活动" in content


def test_all_probe_calls_fail_reports_api_error(monkeypatch):
    _patch_probe(monkeypatch, error_keys={"act-1", "act-2", "act-3"}, merged_error=True)
    content = _call(perspective="outbound_call_analysis")
    assert content.startswith("ERROR: 外呼活动数据查询失败")
    assert "均不是外呼活动" not in content


def test_partial_probe_failure_marks_activity_in_confirm(monkeypatch):
    """合并探测失败回退逐活动探测后，单个活动失败在确认提示中标注。"""
    calls = _patch_probe(monkeypatch, found_keys={"act-1"}, error_keys={"act-2"}, merged_error=True)
    content = _call(perspective="outbound_call_analysis")
    payload = json.loads(content)
    assert payload["status"] == "need_confirm"
    assert payload["non_outbound_query_failed"] == ["短信营销"]
    assert set(payload["non_outbound_activities"]) == {"短信营销", "厅堂活动"}
    merged_calls = [c for c in calls if isinstance(c["act_no"], list)]
    individual_calls = [c for c in calls if isinstance(c["act_no"], str)]
    assert len(merged_calls) == 1, "先尝试一次合并探测"
    assert len(individual_calls) == 3, "回退后逐活动探测 3 个活动"


def test_no_perspective_never_calls_outbound_api(monkeypatch):
    calls = _patch_probe(monkeypatch, found_keys={"act-1", "act-2", "act-3"})
    _patch_pipeline_capture(monkeypatch)
    _call()  # 未指定视角
    assert calls == [], "未指定视角不得调用外呼接口"


def test_mixed_confirmed_end_to_end_merges_outbound_data(monkeypatch):
    """混合确认后走真实 run_report_pipeline：外呼数据并入组件数值，模板链覆盖全部活动。"""
    calls = _patch_probe(monkeypatch, found_keys={"act-1"})
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))
    monkeypatch.setattr(rg, "_finish_report_run", lambda *a, **k: None)
    monkeypatch.setattr(
        rg, "validate_report_html",
        lambda html: SimpleNamespace(
            valid=True, issues=[],
            to_dict=lambda *, retry_count, max_retries: {"valid": True},
        ),
    )

    node_calls = []

    def fake_node(name, update):
        async def node(state):
            node_calls.append(name)
            return dict(update)
        return node

    monkeypatch.setattr(rg, "selected_activity_router_node", fake_node("router", {"next_agent": "x"}))
    monkeypatch.setattr(rg, "outbound_activity_data_fetch_node", fake_node("outbound_fetch", {"next_agent": "x"}))
    monkeypatch.setattr(rg, "template_list_fetch_node", fake_node("template_list", {"next_agent": "x"}))
    monkeypatch.setattr(rg, "template_matching_node", fake_node("template_matching", {"next_agent": "x"}))
    monkeypatch.setattr(rg, "component_value_fetch_node", fake_node(
        "component_fetch",
        {"component_values": {"component_values": {"转化率": [1]}}, "next_agent": "x"},
    ))
    async def fake_cleanup(state):
        return {"component_values": state.get("component_values") or {}, "next_agent": "x"}

    monkeypatch.setattr(rg, "component_value_cleanup_node", fake_cleanup)
    monkeypatch.setattr(rg, "activity_template_matching_node", fake_node(
        "activity_template", {"activity_template_match_result": {"template_name": "多活动分析模板"}, "next_agent": "x"},
    ))
    monkeypatch.setattr(rg, "marketing_report_synthesis_node", fake_node(
        "synthesis", {"html_report": "<html><body>ok</body></html>", "next_agent": "supervisor"},
    ))

    # 第一次调用：need_confirm
    first = json.loads(_call(perspective="outbound_call_analysis"))
    assert first["status"] == "need_confirm"
    assert node_calls == []

    # 用户确认后：完整链路
    second = json.loads(_content_of(_call(perspective="outbound_call_analysis", confirm_mixed=True)))
    assert second["status"] == "ok"
    assert "outbound_fetch" not in node_calls, "探测已取数，不得再调外呼查询节点"
    assert "template_matching" in node_calls and "component_fetch" in node_calls
    assert len(calls) == 2, "两次 generate_report 各一次合并探测"


def test_merged_probe_exception_falls_back_to_individual(monkeypatch):
    def fake_fetch(params):
        if isinstance(params["act_no"], list):
            raise ConnectionError("网络不可达")
        return SimpleNamespace(success=True, data={"matched": False}, error="")

    monkeypatch.setattr(rg, "fetch_outbound_activity_data", fake_fetch)
    _patch_pipeline_capture(monkeypatch)
    content = _call(perspective="outbound_call_analysis")
    assert "所选的活动均不是外呼活动" in content
