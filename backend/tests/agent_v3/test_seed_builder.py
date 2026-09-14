"""generate_report seed 构建契约测试（指向 agent_v3 impl 层）。

seed 是 v2 与旧报告管线之间的唯一差异面：旧节点对 state 键敏感
（report_history_enabled / selected_report_activity_ids / marketing_intent 形状），
本文件锁定这些契约。
"""
from __future__ import annotations

from datetime import date

import asyncio
import json

from src.report_pipeline.defaults import RUNTIME_STATE_DEFAULTS
from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import report_gen as rg
from src.agent_v3.tools.impl.report_gen import GenerateReportArgs, build_report_seed


def _ctx(**overrides):
    base = {
        "thread_id": "thread-1",
        "user_id": "u-1",
        "user_name": "张三",
        "org_no": "001",
        "channel": "MF0",
    }
    base.update(overrides)
    return ToolContext(state={}, request=ToolRequestContext(**base))


def _activities():
    return [
        {"activity_id": "act_001", "name": "五一优惠券促活", "start_date": "2026-04-01", "end_date": "2026-05-01"},
        {"activity_id": "act_002", "name": "中秋回馈", "start_date": "2026-09-01", "end_date": "2026-09-30"},
    ]


def test_seed_contains_runtime_defaults_and_identity():
    args = GenerateReportArgs(activity_ids=["act_001", "act_002"], data_source="activity_query")
    seed = build_report_seed({}, _ctx(), args, _activities(), "生成对比报告")

    # RUNTIME_STATE_DEFAULTS 兜底：节点读取的键不得缺失
    for key, default in RUNTIME_STATE_DEFAULTS.items():
        assert key in seed, f"seed 缺少 RUNTIME_STATE_DEFAULTS 键: {key}"

    assert seed["request_id"], "request_id 必须非空"
    assert seed["thread_id"] == "thread-1"
    assert seed["user_id"] == "u-1"
    assert seed["org_no"] == "001"
    assert seed["channel"] == "MF0"
    assert seed["report_history_enabled"] is True
    assert seed["selected_report_activity_ids"] == ["act_001", "act_002"]
    assert seed["activity_list"] == _activities()


def test_seed_request_id_unique_per_report():
    args = GenerateReportArgs(activity_ids=["act_001"], data_source="activity_query")
    seed1 = build_report_seed({}, _ctx(), args, _activities()[:1], "")
    seed2 = build_report_seed({}, _ctx(), args, _activities()[:1], "")
    assert seed1["request_id"] != seed2["request_id"]


def test_seed_marketing_intent_shape_and_date_range():
    args = GenerateReportArgs(activity_ids=["act_001", "act_002"], data_source="activity_query")
    seed = build_report_seed({}, _ctx(), args, _activities(), "", today=date(2026, 10, 15))
    intent = seed["marketing_intent"]
    assert intent["intent_type"] == "activity_analysis"
    # period 取活动起止日期的并集（两个活动在 2026-10-15 均已结束）
    assert intent["period"] == {"start_date": "2026-04-01", "end_date": "2026-09-30"}
    assert intent["scene"] == "activity_analysis"


def test_seed_period_uses_t_minus_2_when_activity_ongoing():
    args = GenerateReportArgs(activity_ids=["act_001", "act_002"], data_source="activity_query")
    seed = build_report_seed({}, _ctx(), args, _activities(), "", today=date(2026, 7, 21))
    assert seed["marketing_intent"]["period"] == {"start_date": "2026-04-01", "end_date": "2026-07-19"}


def test_resolve_activities_reports_missing_ids():
    """快照只保留最近一次查询结果，"旧活动 + 新活动"完整编号中旧活动未命中时，
    返回未命中列表交由回源补齐（不得静默忽略，否则生成范围残缺的报告）。"""
    state = {"activity_list": [_activities()[1]]}  # 快照里只有 act_002
    args = GenerateReportArgs(activity_ids=["act_001", "act_002"], data_source="activity_query")
    activities, missing, error = rg._resolve_activities(state, args)
    assert error == ""
    assert activities == [_activities()[1]]
    assert missing == ["act_001"]


def test_resolve_activities_all_hit_still_works():
    state = {"activity_list": _activities()}
    args = GenerateReportArgs(activity_ids=["act_001", "act_002"], data_source="activity_query")
    activities, missing, error = rg._resolve_activities(state, args)
    assert error == "" and missing == []
    assert len(activities) == 2


async def test_resolve_with_backfill_fetches_missing_from_api(monkeypatch):
    """快照未命中的编号自动回源补齐：一次 generate_report 调用即可成功，
    模型无需重新 search 再调用（已有报告时会因此只弹一次覆盖审批）。"""
    async def fake_query(activity_id, request):
        assert activity_id == "act_001"
        return _activities()[0], ""

    monkeypatch.setattr(
        "src.agent_v3.tools.impl.activity_query.query_activity_by_id", fake_query)
    state = {"activity_list": [_activities()[1]]}
    args = GenerateReportArgs(activity_ids=["act_001", "act_002"], data_source="activity_query")
    activities, error = await rg._resolve_activities_with_backfill(state, args, _ctx())
    assert error == ""
    # 按模型传入的编号顺序合并
    assert activities == _activities()


async def test_resolve_with_backfill_errors_when_api_misses(monkeypatch):
    """回源也查不到（编号无效）时才报错，并指明是哪个编号。"""
    async def fake_query(activity_id, request):
        return None, f"未找到活动 {activity_id}"

    monkeypatch.setattr(
        "src.agent_v3.tools.impl.activity_query.query_activity_by_id", fake_query)
    state = {"activity_list": [_activities()[1]]}
    args = GenerateReportArgs(activity_ids=["act_001", "act_002"], data_source="activity_query")
    activities, error = await rg._resolve_activities_with_backfill(state, args, _ctx())
    assert activities == []
    assert "act_001" in error
    assert "act_002" not in error


def test_seed_messages_is_single_user_message():
    args = GenerateReportArgs(
        activity_ids=["act_001"],
        data_source="activity_query",
        metrics=["roi"],
        analysis_focus="重点关注转化",
    )
    seed = build_report_seed({}, _ctx(), args, _activities()[:1], "看看 ROI")
    assert len(seed["messages"]) == 1
    message = seed["messages"][0]
    assert message["role"] == "user"
    assert "ROI" in message["content"] or "roi" in message["content"]
    assert "重点关注转化" in message["content"]
    assert "五一优惠券促活" in message["content"]


def test_seed_perspective_injects_scene():
    args = GenerateReportArgs(
        activity_ids=["act_001"],
        data_source="activity_query",
        perspective="outbound_call_analysis",
    )
    seed = build_report_seed({}, _ctx(), args, _activities()[:1], "")
    assert "外呼活动分析视角" in seed["marketing_intent"]["scene"]
    assert "接通率" in seed["marketing_intent"]["scene"]


def test_seed_perspective_affects_template_similarity():
    args = GenerateReportArgs(
        activity_ids=["act_001"],
        data_source="activity_query",
        perspective="sms_analysis",
    )
    seed = build_report_seed({}, _ctx(), args, _activities()[:1], "短信视角分析")
    scene = seed["marketing_intent"]["scene"]
    assert "短信营销分析视角" in scene
    assert "点击率" in scene


def test_seed_perspective_keys_and_default_template_mode():
    args = GenerateReportArgs(
        activity_ids=["act_001"], data_source="activity_query", perspective="sms_analysis",
    )
    seed = build_report_seed({}, _ctx(), args, _activities()[:1], "", today=date(2026, 10, 15))
    assert seed["perspective_key"] == "sms_analysis"
    assert seed["perspective_keyword"] == "短信"
    assert seed["outbound_activity_data_map"] == {}
    assert seed["workflow_mode"] == "template_component_report"


def test_seed_no_perspective_never_outbound_first():
    args = GenerateReportArgs(activity_ids=["act_001"], data_source="activity_query")
    seed = build_report_seed({}, _ctx(), args, _activities()[:1], "", today=date(2026, 10, 15))
    assert seed["perspective_key"] == ""
    assert seed["workflow_mode"] == "template_component_report"


def test_seed_single_outbound_hit_presets_direct_mode():
    outbound_map = {"act_001": {"接通率": 0.6}}
    args = GenerateReportArgs(
        activity_ids=["act_001"], data_source="activity_query",
        perspective="outbound_call_analysis",
    )
    seed = build_report_seed(
        {}, _ctx(), args, _activities()[:1], "",
        outbound_map=outbound_map, today=date(2026, 10, 15),
    )
    assert seed["workflow_mode"] == "direct_outbound_report"
    assert seed["outbound_activity_data"] == {"接通率": 0.6}
    assert seed["outbound_activity_data_found"] is True


def test_seed_multi_outbound_hit_presets_mixed_mode():
    outbound_map = {"act_001": {"接通率": 0.6}}
    args = GenerateReportArgs(
        activity_ids=["act_001", "act_002"], data_source="activity_query",
        perspective="outbound_call_analysis",
    )
    seed = build_report_seed(
        {}, _ctx(), args, _activities(), "",
        outbound_map=outbound_map, today=date(2026, 10, 15),
    )
    assert seed["workflow_mode"] == "template_component_report"
    assert seed["outbound_activity_data_map"] == {"act_001": {"接通率": 0.6}}
    assert seed["outbound_activity_data_found"] is False


def test_generate_report_reads_original_user_text_from_request_context(monkeypatch):
    """Task8 修复回归：original_user_text 只从 ToolContext.request 读取，
    壳层不再把它注入 state 快照。"""
    captured: dict = {}

    async def fake_pipeline(seed, writer):
        captured.update(seed)
        return {"html_report": "<html><body>报告</body></html>"}

    monkeypatch.setattr(rg, "run_report_pipeline", fake_pipeline)
    monkeypatch.setattr(rg, "_finish_report_run", lambda *a, **k: None)

    ctx = ToolContext(
        # state 中故意不放 original_user_text：即使放了也不得被读取
        state={"activity_list": _activities()},
        request=ToolRequestContext(
            thread_id="thread-1",
            request_id="req-turn-1",
            original_user_text="把五一活动加入报告",
        ),
        tool_call_id="call-1",
    )
    result = asyncio.run(
        rg.generate_report(ctx, activity_ids=["act_001"], data_source="activity_query")
    )

    payload = json.loads(result.content)
    assert payload["status"] == "ok"
    assert "把五一活动加入报告" in captured["original_user_text"]
    assert "把五一活动加入报告" in captured["messages"][0]["content"]
