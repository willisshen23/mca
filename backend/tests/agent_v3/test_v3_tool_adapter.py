"""agent_v3 工具壳契约测试：假 impl + 假会话，不触 openjiuwen 运行时与 LLM。

壳层契约（agent_v3/tools/__init__.py 的 _run 模式）：
①业务参数原样透传给 impl；②ToolContext.state 为会话快照七键（不含 turn 级键，
  turn 级 request_id/original_user_text 走 ToolRequestContext）；
③ToolOutcome.state_updates 写回 session.update_state；④impl 返回 str 时直传。
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from src.agent_v3 import tools as v3_tools
from src.agent_v3.request_context import reset_request_context, set_request_context
from src.agent_v3.tools.impl import ToolContext, ToolOutcome
from src.agent_v3.tools.impl import activity_query as impl_activity_query
from src.agent_v3.tools.impl import analysis_queue as impl_analysis_queue
from src.agent_v3.tools.impl import skill as impl_skill
from src.agent_v3.tools.impl.context import ToolRequestContext

#: 壳层会话快照七键（与 v3_tools._SESSION_STATE_KEYS 对齐）
_SEVEN_SESSION_KEYS = (
    "analysis_queue",
    "activity_list",
    "report_context",
    "html_report",
    "uploaded_activity_dataset",
    "data_summary",
    "formatted_output_path",
)


class _FakeSession:
    """SimpleNamespace 式假会话：记录 update_state 与 write_custom_stream。"""

    def __init__(self):
        self._data = {}
        self.stream_events = []

    def get_state(self, key=None):
        return self._data.get(key)

    def update_state(self, data):
        self._data.update(data)

    async def write_custom_stream(self, event):
        self.stream_events.append(event)


@pytest.fixture
def fake_session(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(v3_tools, "get_current_session", lambda: session)
    return session


def _seed_full_session(session: _FakeSession) -> dict:
    """七键 + 一个白名单外键（不应进入快照）。"""
    payload = {key: f"value-{key}" for key in _SEVEN_SESSION_KEYS}
    payload["activity_list"] = [{"activity_id": "A9"}]
    payload["unrelated_secret"] = "不应入快照"
    session.update_state(payload)
    return payload


async def test_business_params_passthrough(fake_session, monkeypatch):
    """①业务参数原样透传 impl（含调用方未显式给出的默认值）。"""
    seen = {}

    async def fake_impl(ctx, category: str = "", keyword: str = ""):
        seen["ctx"] = ctx
        seen["category"] = category
        seen["keyword"] = keyword
        return "ok"

    monkeypatch.setattr(impl_skill, "get_available_skills", fake_impl)
    result = await v3_tools.get_available_skills._func(category="活动分析", keyword="转化")

    assert result == "ok"
    assert isinstance(seen["ctx"], ToolContext)
    assert seen["category"] == "活动分析"
    assert seen["keyword"] == "转化"


async def test_state_snapshot_seven_session_keys(fake_session, monkeypatch):
    """②ToolContext.state 恰含会话快照七键；白名单外键与 turn 级键均不入快照。"""
    _seed_full_session(fake_session)
    token = set_request_context({"request_id": "r1", "original_user_text": "原文"})
    seen = {}

    async def fake_impl(ctx, activity_id: str):
        seen["state"] = ctx.state
        return "ok"

    monkeypatch.setattr(impl_activity_query, "get_activity_detail", fake_impl)
    try:
        result = await v3_tools.get_activity_detail._func(activity_id="A9")
    finally:
        reset_request_context(token)

    assert result == "ok"
    state = seen["state"]
    for key in _SEVEN_SESSION_KEYS:
        assert key in state, f"快照缺会话键 {key}"
    assert state["activity_list"] == [{"activity_id": "A9"}]
    assert "unrelated_secret" not in state
    # turn 级键已迁移到 ToolRequestContext，不再注入 state（_TURN_STATE_KEYS 已删）
    assert "request_id" not in state
    assert "original_user_text" not in state


async def test_request_contextvar_builds_tool_request_context(fake_session, monkeypatch):
    """ToolRequestContext 由 request_context ContextVar 过滤 model_fields 组装。"""
    token = set_request_context({
        "user_id": "U1",
        "org_no": "3201",
        "thread_id": "t-1",
        "request_id": "r-1",
        "original_user_text": "帮我看看外呼活动",
        "unknown_key": "应被过滤",
    })
    seen = {}

    async def fake_impl(ctx, activity_id: str):
        seen["request"] = ctx.request
        return "ok"

    monkeypatch.setattr(impl_activity_query, "get_activity_detail", fake_impl)
    try:
        await v3_tools.get_activity_detail._func(activity_id="A9")
    finally:
        reset_request_context(token)

    request = seen["request"]
    assert isinstance(request, ToolRequestContext)
    assert request.user_id == "U1"
    assert request.org_no == "3201"
    assert request.request_id == "r-1"
    assert request.original_user_text == "帮我看看外呼活动"
    assert not hasattr(request, "unknown_key")


async def test_tool_outcome_state_updates_written_to_session(fake_session, monkeypatch):
    """③ToolOutcome.state_updates 写回 session；content 作为工具返回。"""
    new_queue = [{"activity_id": "A1"}]

    async def fake_impl(ctx, activity_ids):
        return ToolOutcome('{"status":"ok"}', {"analysis_queue": new_queue})

    monkeypatch.setattr(impl_analysis_queue, "remove_from_analysis_queue", fake_impl)
    result = await v3_tools.remove_from_analysis_queue._func(activity_ids=["A1"])

    assert result == '{"status":"ok"}'
    assert fake_session.get_state("analysis_queue") == new_queue


async def test_plain_str_result_passthrough(fake_session, monkeypatch):
    """④impl 返回 str 时直传，且不触发任何会话写入。"""
    async def fake_impl(ctx, activity_ids):
        return "plain-text"

    monkeypatch.setattr(impl_analysis_queue, "remove_from_analysis_queue", fake_impl)
    result = await v3_tools.remove_from_analysis_queue._func(activity_ids=["A1"])

    assert result == "plain-text"
    assert fake_session._data == {}


async def test_state_updates_dropped_with_warning_when_no_session(monkeypatch, caplog):
    """无会话时 state_updates 丢弃并 warn（保留 invoke_v2_tool 既有告警行为）。"""
    def _no_session():
        raise RuntimeError("no session")

    monkeypatch.setattr(v3_tools, "get_current_session", _no_session)
    seen = {}

    async def fake_impl(ctx, activity_ids):
        seen["state"] = ctx.state
        return ToolOutcome("content", {"analysis_queue": []})

    monkeypatch.setattr(impl_analysis_queue, "remove_from_analysis_queue", fake_impl)
    with caplog.at_level(logging.WARNING, logger="njbank.agent"):
        result = await v3_tools.remove_from_analysis_queue._func(activity_ids=["A1"])

    assert result == "content"
    assert seen["state"] == {}
    assert any("状态更新被丢弃" in rec.message for rec in caplog.records)


async def test_write_stream_bridges_to_session_custom_stream(fake_session, monkeypatch):
    """write_stream 闭包经 run_coroutine_threadsafe 桥到 session.write_custom_stream。"""
    async def fake_impl(ctx, category: str = "", keyword: str = ""):
        ctx.write_stream({"type": "progress", "stage": "testing"})
        return "ok"

    monkeypatch.setattr(impl_skill, "get_available_skills", fake_impl)
    result = await v3_tools.get_available_skills._func()
    assert result == "ok"

    for _ in range(50):
        if fake_session.stream_events:
            break
        await asyncio.sleep(0.01)
    assert fake_session.stream_events == [{"type": "progress", "stage": "testing"}]


async def test_write_stream_noop_without_session(monkeypatch):
    """无会话时 write_stream 为 no-op，impl 调用不炸。"""
    def _no_session():
        raise RuntimeError("no session")

    monkeypatch.setattr(v3_tools, "get_current_session", _no_session)

    async def fake_impl(ctx, category: str = "", keyword: str = ""):
        ctx.write_stream({"type": "progress"})
        return "ok"

    monkeypatch.setattr(impl_skill, "get_available_skills", fake_impl)
    assert await v3_tools.get_available_skills._func() == "ok"


def test_search_activities_card_description_not_truncated():
    """openjiuwen @tool 在 docstring 首个空行处截断 description：壳 docstring 必须单段。

    断言 card.description 含 "参数" 与 "limit"，证明参数语义段落未被截断、可达模型。
    """
    description = v3_tools.search_activities.card.description
    assert "参数" in description
    assert "limit" in description


def test_generate_report_data_source_constrained_by_literal():
    """generate_report 壳的 data_source 必须以 Literal 约束（impl 无运行时校验）。"""
    props = v3_tools.generate_report.card.input_params["properties"]
    assert props["data_source"]["enum"] == ["activity_query", "uploaded", "analysis_queue"]


async def test_write_todos_updates_session(fake_session):
    """write_todos 为 v3 原生壳（无 impl）：直接写会话 todos。"""
    result = await v3_tools.write_todos._func(todos=["第一步", "第二步"])
    assert result == "已记录 2 条待办"
    assert fake_session.get_state("todos") == ["第一步", "第二步"]
