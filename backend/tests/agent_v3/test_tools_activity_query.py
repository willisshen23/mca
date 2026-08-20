"""search_activities / get_activity_detail 工具测试（mock 服务层，无网络；指向 agent_v3 impl 层）。"""
from __future__ import annotations

import asyncio
import json

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import activity_query as aq
from src.infrastructure.integrations.bank_marketing.schemas import ApiResult


def _ctx(state=None, **req):
    return ToolContext(state=state or {}, request=ToolRequestContext(**req), tool_call_id="call-1")


def _api_result(items, success=True, error=""):
    return ApiResult(success=success, data=items, error=error)


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


def test_search_activities_merges_within_same_request(monkeypatch):
    """同一轮请求内多次按名查询：结果按 activity_id 去重合并（新结果在前），
    避免逐个活动名查询时后一次覆盖前一次，路由只能看到最后一个活动。"""
    state = {
        "activity_list": [
            {"activity_id": "act_001", "name": "个养缴存营销-滨江支行", "row_number": 1},
        ],
        "activity_list_request_id": "req-1",
    }
    monkeypatch.setattr(
        aq,
        "fetch_activity_list",
        lambda params: _api_result([{"actNo": "act_002", "actName": "个养开户营销-滨江支行"}]),
    )

    result = asyncio.run(aq.search_activities(_ctx(state=state, request_id="req-1"), keyword="个养开户营销-滨江支行"))

    update = result.state_updates
    ids = [item["activity_id"] for item in update["activity_list"]]
    assert ids == ["act_002", "act_001"]
    assert update["activity_list_request_id"] == "req-1"
    # 工具内容（给模型/用户看的本次查询结果）不受合并影响
    payload = json.loads(result.content)
    assert payload["count"] == 1


def test_search_activities_replaces_on_new_request(monkeypatch):
    """跨请求（新一轮对话）查询整体替换，保持"最近查询结果"语义，
    避免上一轮的旧活动残留影响本轮路由。"""
    state = {
        "activity_list": [
            {"activity_id": "act_001", "name": "个养缴存营销-滨江支行", "row_number": 1},
        ],
        "activity_list_request_id": "req-1",
    }
    monkeypatch.setattr(
        aq,
        "fetch_activity_list",
        lambda params: _api_result([{"actNo": "act_002", "actName": "个养开户营销-滨江支行"}]),
    )

    result = asyncio.run(aq.search_activities(_ctx(state=state, request_id="req-2"), keyword="个养开户营销-滨江支行"))

    update = result.state_updates
    ids = [item["activity_id"] for item in update["activity_list"]]
    assert ids == ["act_002"]
    assert update["activity_list_request_id"] == "req-2"


def test_search_activities_merge_dedupes_same_activity(monkeypatch):
    """同一轮内重复查询同一活动时不产生重复条目。"""
    state = {
        "activity_list": [
            {"activity_id": "act_001", "name": "个养缴存营销-滨江支行", "row_number": 1},
            {"activity_id": "act_009", "name": "年终回馈", "row_number": 2},
        ],
        "activity_list_request_id": "req-1",
    }
    monkeypatch.setattr(
        aq,
        "fetch_activity_list",
        lambda params: _api_result([{"actNo": "act_001", "actName": "个养缴存营销-滨江支行"}]),
    )

    result = asyncio.run(aq.search_activities(_ctx(state=state, request_id="req-1"), keyword="个养缴存"))

    ids = [item["activity_id"] for item in result.state_updates["activity_list"]]
    assert ids == ["act_001", "act_009"]


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
