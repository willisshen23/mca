"""search_activities / get_activity_detail 工具测试（mock 服务层，无网络）。

impl 层直调 + 壳层 _run 写时合并（activity_list 的并集合并在壳层写入会话时
执行，见 tools/__init__.py 的 _merge_activity_list_for_write）。
"""
from __future__ import annotations

import asyncio
import json

from src.agent_v3 import tools as tools_shell
from src.agent_v3.request_context import reset_request_context, set_request_context
from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import activity_query as aq
from src.infrastructure.integrations.bank_marketing.schemas import ApiResult


def _ctx(state=None, **req):
    return ToolContext(state=state or {}, request=ToolRequestContext(**req), tool_call_id="call-1")


def _api_result(items, success=True, error=""):
    return ApiResult(success=success, data=items, error=error)


class _FakeSession:
    """最小会话替身：get_state/update_state 同步读写内存字典。"""

    def __init__(self, state=None):
        self.state = dict(state or {})

    def get_state(self, key):
        return self.state.get(key)

    def update_state(self, updates):
        self.state.update(updates)


def _shell_search(monkeypatch, session, keyword, request_id="req-1"):
    """经壳层 _run 执行一次 search_activities（含写时合并与状态写回）。"""
    monkeypatch.setattr(tools_shell, "get_current_session", lambda: session)
    token = set_request_context({"request_id": request_id})
    try:
        return asyncio.run(
            tools_shell._run(aq.search_activities, dict(keyword=keyword)))
    finally:
        reset_request_context(token)


def test_search_activities_success(monkeypatch):
    items = [
        {"actNo": "act_001", "actName": "五一优惠券促活", "channel": "短信", "actStartDt": "2026-04-01", "actEndDt": "2026-05-01"},
        {"actNo": "act_002", "actName": "中秋回馈", "channel": "外呼", "actStartDt": "2026-09-01", "actEndDt": "2026-09-30"},
        # 重复 id，应被去重
        {"actNo": "act_001", "actName": "五一优惠券促活", "channel": "短信"},
    ]
    monkeypatch.setattr(aq, "fetch_activity_list", lambda params: _api_result(items))

    result = asyncio.run(aq.search_activities(_ctx(), keyword="优惠券"))

    update = result.state_updates
    assert len(update["activity_list"]) == 2
    assert update["activity_list"][0]["activity_id"] == "act_001"
    assert update["activity_list"][0]["name"] == "五一优惠券促活"
    # 合并不在 impl 内执行：state_updates 只带本次结果，由壳层写时合并
    assert result.merge_keys == ("activity_list",)
    payload = json.loads(result.content)
    assert payload["count"] == 2


def test_search_activities_passes_requester_oa_number_from_context(monkeypatch):
    captured = {}

    def fake_fetch(params):
        captured.update(params)
        return _api_result([{"actNo": "act_001", "actName": "测试活动"}])

    monkeypatch.setattr(aq, "fetch_activity_list", fake_fetch)

    asyncio.run(aq.search_activities(_ctx(user_id="OA003"), keyword="测试"))

    assert captured["userNo"] == "OA003"


def test_search_activities_passes_src_sys_no_from_context(monkeypatch):
    """URL 挂参 srcSysNo 经上下文透传到活动查询请求（缺省时不下发，由客户端走配置默认）。"""
    captured = {}

    def fake_fetch(params):
        captured.update(params)
        return _api_result([{"actNo": "act_001", "actName": "测试活动"}])

    monkeypatch.setattr(aq, "fetch_activity_list", fake_fetch)

    asyncio.run(aq.search_activities(_ctx(user_id="OA003", src_sys_no="S05"), keyword="测试"))
    assert captured["srcSysNo"] == "S05"

    captured.clear()
    asyncio.run(aq.search_activities(_ctx(user_id="OA003"), keyword="测试"))
    assert "srcSysNo" not in captured


def test_get_activity_detail_passes_src_sys_no_from_context(monkeypatch):
    captured = {}

    def fake_fetch(params):
        captured.update(params)
        return _api_result([{"actNo": "act_009", "actName": "年终回馈"}])

    monkeypatch.setattr(aq, "fetch_activity_list", fake_fetch)

    asyncio.run(aq.get_activity_detail(_ctx(user_id="OA003", src_sys_no="S05"), activity_id="act_009"))

    assert captured["srcSysNo"] == "S05"


def test_run_merges_sequential_searches_within_same_request(monkeypatch):
    """同一轮请求内多次按名查询：写回会话时按 activity_id 去重合并（新结果在前），
    避免逐个活动名查询时后一次覆盖前一次，路由只能看到最后一个活动。"""
    session = _FakeSession()
    monkeypatch.setattr(
        aq,
        "fetch_activity_list",
        lambda params: _api_result([{"actNo": "act_001", "actName": "个养缴存营销-滨江支行"}]),
    )
    _shell_search(monkeypatch, session, "个养缴存营销-滨江支行")
    monkeypatch.setattr(
        aq,
        "fetch_activity_list",
        lambda params: _api_result([{"actNo": "act_002", "actName": "个养开户营销-滨江支行"}]),
    )
    content = _shell_search(monkeypatch, session, "个养开户营销-滨江支行")

    ids = [item["activity_id"] for item in session.state["activity_list"]]
    assert ids == ["act_002", "act_001"]
    assert session.state["activity_list_request_id"] == "req-1"
    # 工具内容（给模型/用户看的本次查询结果）不受合并影响
    payload = json.loads(content)
    assert payload["count"] == 1


def test_run_replaces_on_new_request(monkeypatch):
    """跨请求（新一轮对话）查询整体替换，保持"最近查询结果"语义，
    避免上一轮的旧活动残留影响本轮路由。"""
    session = _FakeSession({
        "activity_list": [
            {"activity_id": "act_001", "name": "个养缴存营销-滨江支行", "row_number": 1},
        ],
        "activity_list_request_id": "req-1",
    })
    monkeypatch.setattr(
        aq,
        "fetch_activity_list",
        lambda params: _api_result([{"actNo": "act_002", "actName": "个养开户营销-滨江支行"}]),
    )

    _shell_search(monkeypatch, session, "个养开户营销-滨江支行", request_id="req-2")

    ids = [item["activity_id"] for item in session.state["activity_list"]]
    assert ids == ["act_002"]
    assert session.state["activity_list_request_id"] == "req-2"


def test_run_merge_dedupes_same_activity(monkeypatch):
    """同一轮内重复查询同一活动时不产生重复条目。"""
    session = _FakeSession({
        "activity_list": [
            {"activity_id": "act_001", "name": "个养缴存营销-滨江支行", "row_number": 1},
            {"activity_id": "act_009", "name": "年终回馈", "row_number": 2},
        ],
        "activity_list_request_id": "req-1",
    })
    monkeypatch.setattr(
        aq,
        "fetch_activity_list",
        lambda params: _api_result([{"actNo": "act_001", "actName": "个养缴存营销-滨江支行"}]),
    )

    _shell_search(monkeypatch, session, "个养缴存")

    ids = [item["activity_id"] for item in session.state["activity_list"]]
    assert ids == ["act_001", "act_009"]


def test_run_parallel_searches_both_survive(monkeypatch):
    """回归：LLM 单条消息并行发起两次 search_activities 时，两个 impl 读到的
    state 快照都早于任何写入（都看到空 activity_list），合并必须在壳层写回时
    执行——否则 last-write-wins 只剩一个活动，路由退化为单活动分析。"""
    session = _FakeSession()
    by_keyword = {
        "个养缴存营销-滨江支行": [{"actNo": "act_001", "actName": "个养缴存营销-滨江支行"}],
        "个养开户营销-滨江支行": [{"actNo": "act_002", "actName": "个养开户营销-滨江支行"}],
    }
    monkeypatch.setattr(
        aq,
        "fetch_activity_list",
        lambda params: _api_result(by_keyword[params["actName"]]),
    )
    monkeypatch.setattr(tools_shell, "get_current_session", lambda: session)
    token = set_request_context({"request_id": "req-1"})
    try:
        async def run_both():
            await asyncio.gather(
                tools_shell._run(aq.search_activities, dict(keyword="个养缴存营销-滨江支行")),
                tools_shell._run(aq.search_activities, dict(keyword="个养开户营销-滨江支行")),
            )
        asyncio.run(run_both())
    finally:
        reset_request_context(token)

    ids = {item["activity_id"] for item in session.state["activity_list"]}
    assert ids == {"act_001", "act_002"}


def test_search_activities_api_failure_returns_error(monkeypatch):
    monkeypatch.setattr(aq, "fetch_activity_list", lambda params: _api_result(None, success=False, error="timeout"))

    content = asyncio.run(aq.search_activities(_ctx(), keyword="x"))

    assert isinstance(content, str)
    assert content.startswith("ERROR:")
    assert "timeout" in content


def test_search_activities_empty_result(monkeypatch):
    monkeypatch.setattr(aq, "fetch_activity_list", lambda params: _api_result([]))

    content = asyncio.run(aq.search_activities(_ctx(), keyword="不存在"))

    assert content.startswith("ERROR:")
    assert "未查询到" in content


def test_get_activity_detail_from_recent_search():
    state = {
        "activity_list": [
            {"activity_id": "act_001", "name": "五一优惠券促活", "channel": "短信"},
        ]
    }
    content = asyncio.run(aq.get_activity_detail(_ctx(state=state), activity_id="act_001"))

    payload = json.loads(content)
    assert payload["source"] == "recent_search"
    assert payload["activity"]["name"] == "五一优惠券促活"


def test_get_activity_detail_fallback_to_api(monkeypatch):
    monkeypatch.setattr(
        aq,
        "fetch_activity_list",
        lambda params: _api_result([{"actNo": "act_009", "actName": "年终回馈"}]),
    )

    content = asyncio.run(aq.get_activity_detail(_ctx(), activity_id="act_009"))

    payload = json.loads(content)
    assert payload["source"] == "bank_api"
    assert payload["activity"]["activity_id"] == "act_009"


def test_get_activity_detail_not_found(monkeypatch):
    monkeypatch.setattr(aq, "fetch_activity_list", lambda params: _api_result([]))

    content = asyncio.run(aq.get_activity_detail(_ctx(), activity_id="act_404"))

    assert content.startswith("ERROR:")
    assert "act_404" in content
