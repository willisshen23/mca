"""ToolCallLimitRail / ToolProgressRail 单元测试（假 ctx，不起 agent）。"""

from types import SimpleNamespace

import pytest

from src.agent_v3.rails import ToolCallLimitRail, ToolProgressRail


class _FakeSession:
    def __init__(self, state=None, session_id="s-1"):
        self._state = state or {}
        self._session_id = session_id
        self.custom_frames = []

    def get_session_id(self):
        return self._session_id

    def get_state(self, key=None):
        return self._state.get(key)

    async def write_custom_stream(self, data):
        self.custom_frames.append(data)


def _tool_ctx(tool_name, session=None, tool_args=None, tool_result=None):
    tool_call = SimpleNamespace(id="call-1")
    return SimpleNamespace(
        extra={},
        session=session,
        inputs=SimpleNamespace(
            tool_name=tool_name,
            tool_args=tool_args or {},
            tool_call=tool_call,
            tool_result=tool_result,
            tool_msg=None,
        ),
    )


def _invoke_ctx(session=None, query="q", conversation_id=None):
    return SimpleNamespace(
        session=session,
        inputs=SimpleNamespace(query=query, conversation_id=conversation_id),
    )


async def test_limit_rail_skips_after_max():
    session = _FakeSession(session_id="s-1")
    rail = ToolCallLimitRail(max_calls=2)
    await rail.before_invoke(_invoke_ctx(session))
    for _ in range(2):
        ctx = _tool_ctx("search_activities", session)
        await rail.before_tool_call(ctx)
        assert ctx.extra.get("_skip_tool") is not True
    ctx3 = _tool_ctx("search_activities", session)
    await rail.before_tool_call(ctx3)
    assert ctx3.extra["_skip_tool"] is True
    assert "不要再调用" in ctx3.inputs.tool_result
    assert ctx3.inputs.tool_msg is not None


async def test_limit_rail_resets_per_invoke():
    session = _FakeSession(session_id="s-1")
    rail = ToolCallLimitRail(max_calls=1)
    await rail.before_invoke(_invoke_ctx(session, query="q1"))
    ctx = _tool_ctx("t", session)
    await rail.before_tool_call(ctx)
    ctx2 = _tool_ctx("t", session)
    await rail.before_tool_call(ctx2)
    assert ctx2.extra.get("_skip_tool") is True
    # 新一轮 invoke 重置
    await rail.before_invoke(_invoke_ctx(session, query="q2"))
    ctx3 = _tool_ctx("t", session)
    await rail.before_tool_call(ctx3)
    assert ctx3.extra.get("_skip_tool") is not True


async def test_limit_rail_counts_are_isolated_per_session():
    """两个会话并发交替调用：A 超限不影响 B 的额度。"""
    session_a = _FakeSession(session_id="A")
    session_b = _FakeSession(session_id="B")
    rail = ToolCallLimitRail(max_calls=1)
    await rail.before_invoke(_invoke_ctx(session_a))
    await rail.before_invoke(_invoke_ctx(session_b))
    # A 用掉唯一额度
    await rail.before_tool_call(_tool_ctx("t", session_a))
    ctx_a_over = _tool_ctx("t", session_a)
    await rail.before_tool_call(ctx_a_over)
    assert ctx_a_over.extra.get("_skip_tool") is True
    # B 的额度不受 A 影响
    ctx_b = _tool_ctx("t", session_b)
    await rail.before_tool_call(ctx_b)
    assert ctx_b.extra.get("_skip_tool") is not True
    # B 超限也只影响自己
    ctx_b_over = _tool_ctx("t", session_b)
    await rail.before_tool_call(ctx_b_over)
    assert ctx_b_over.extra.get("_skip_tool") is True
    # A 新一轮 invoke 只重置 A
    await rail.before_invoke(_invoke_ctx(session_a, query="q-a2"))
    ctx_a_new = _tool_ctx("t", session_a)
    await rail.before_tool_call(ctx_a_new)
    assert ctx_a_new.extra.get("_skip_tool") is not True
    # B 仍处于超限状态
    ctx_b_still = _tool_ctx("t", session_b)
    await rail.before_tool_call(ctx_b_still)
    assert ctx_b_still.extra.get("_skip_tool") is True


async def test_progress_rail_emits_running_done_and_state():
    session = _FakeSession({"analysis_queue": [{"activity_id": "A1"}],
                            "report_context": {"report_id": "r1", "data_snapshot": {"big": 1}}})
    rail = ToolProgressRail()
    await rail.before_tool_call(_tool_ctx("add_to_analysis_queue", session,
                                          tool_args={"activity_ids": ["A1"]}))
    await rail.after_tool_call(_tool_ctx("add_to_analysis_queue", session,
                                         tool_result='{"status":"ok"}'))
    kinds = [f.get("njbank") for f in session.custom_frames]
    assert kinds == ["tool_progress", "tool_progress", "state_update"]
    running, done, state = session.custom_frames
    assert running["status"] == "running" and running["tool"] == "add_to_analysis_queue"
    assert done["status"] == "done"
    assert state["data"]["analysis_queue"] == [{"activity_id": "A1"}]
    # report_context 剥 data_snapshot
    assert "data_snapshot" not in state["data"]["report_context"]


async def test_progress_rail_suppresses_generate_report():
    session = _FakeSession()
    rail = ToolProgressRail()
    await rail.before_tool_call(_tool_ctx("generate_report", session))
    await rail.after_tool_call(_tool_ctx("generate_report", session, tool_result="ok"))
    assert all(f.get("njbank") != "tool_progress" for f in session.custom_frames)


async def test_progress_rail_parses_json_string_tool_args():
    """openjiuwen 的 tool_args 是 JSON 字符串，running 帧的 args_summary 须解析出来。"""
    session = _FakeSession()
    rail = ToolProgressRail()
    await rail.before_tool_call(_tool_ctx(
        "add_to_analysis_queue", session,
        tool_args='{"activity_ids": ["A1"]}'))
    running = session.custom_frames[0]
    assert running["status"] == "running"
    assert running["args_summary"] == {"activity_ids": ["A1"]}


async def test_progress_rail_invalid_json_tool_args_falls_back_to_empty():
    session = _FakeSession()
    rail = ToolProgressRail()
    await rail.before_tool_call(_tool_ctx("search_activities", session,
                                          tool_args="{not json"))
    assert session.custom_frames[0]["args_summary"] == {}
