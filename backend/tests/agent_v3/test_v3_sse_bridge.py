"""v3 sse_bridge 帧映射测试：罐头帧序列 → 断言 SSE 帧文本。"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from openjiuwen.core.session.stream.base import CustomSchema, OutputSchema

from src.agent_v3 import sessions as v3_sessions
from src.agent_v3.events import sse_bridge as v3_bridge


class _FakeRunnerStream:
    """模拟 Runner.run_agent_streaming 的异步帧序列。"""

    def __init__(self, chunks):
        self._chunks = chunks

    def __call__(self, agent, inputs, *, session=None, stream_modes=None):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


def _out(t, payload):
    return OutputSchema(type=t, index=0, payload=payload)


def _custom(data):
    return CustomSchema(**data)


def _parse(frame_text):
    assert frame_text.startswith("data: ")
    return json.loads(frame_text[len("data: "):])


async def _collect(chunks, thread_id="t1"):
    orig = v3_bridge.Runner.run_agent_streaming
    v3_bridge.Runner.run_agent_streaming = _FakeRunnerStream(chunks)
    try:
        frames = []
        async for f in v3_bridge.stream_v3_events(
                agent=None, session=None, inputs={"query": "hi"},
                request_id="r1", thread_id=thread_id, is_cancelled=lambda: False):
            frames.append(_parse(f))
        return frames
    finally:
        v3_bridge.Runner.run_agent_streaming = orig


def setup_function():
    v3_sessions.reset_sessions()


async def test_error_answer_raises_instead_of_silent_success():
    """框架 stream_process 吞异常后以 answer 帧下发 {"output": str(e), "result_type": "error"}。
    bridge 必须抛出（走 runtime 失败路径：turn 记 failed + 前端 error 帧），
    绝不能当正常 answer 发 done——否则用户看到"成功"的空/错误回复，
    且本轮 context 未落库，后续每轮都被当成第一个问题（2026-08-18 联调实测）。"""
    with pytest.raises(RuntimeError, match="LLM client 创建失败"):
        await _collect([
            _out("answer", {"output": "LLM client 创建失败: verify_ssl",
                            "result_type": "error"}),
        ])


async def test_llm_output_and_answer_to_done():
    frames = await _collect([
        _out("llm_output", {"content": "你", "result_type": "stream"}),
        _out("llm_output", {"content": "好", "result_type": "stream"}),
        _out("llm_usage", {"total_tokens": 10}),
        _out("answer", {"output": "你好", "result_type": "answer"}),
    ])
    done = frames[-1]
    assert done["type"] == "done"
    assert done["payload"]["final_response"] == "你好"
    assert done["payload"]["awaiting_approval"] is False
    assert done["payload"]["request_id"] == "r1"


async def test_interaction_to_approval_and_pending():
    """用真实 InteractionOutput/ToolCallInterruptRequest 对象（非替身）——
    请求内容在 InteractionOutput.value（联调实测：取 .payload 会拿到空参数）。"""
    from openjiuwen.core.session.interaction.interaction import InteractionOutput
    from openjiuwen.core.single_agent.interrupt.response import ToolCallInterruptRequest

    interaction_payload = InteractionOutput(
        id="int-1",
        value=ToolCallInterruptRequest(
            message="请确认是否执行「修改报告」",
            tool_name="modify_report",
            tool_call_id="call-1",
            tool_args='{"free_instruction":"改标题"}',
        ),
    )
    frames = await _collect([_out("__interaction__", interaction_payload)])
    approval = frames[0]
    assert approval["type"] == "approval_required"
    assert approval["payload"]["tool"] == "modify_report"
    assert approval["payload"]["args"] == {"free_instruction": "改标题"}
    assert approval["payload"]["description"] == "请确认是否执行「修改报告」"
    assert approval["payload"]["display_name"] == "修改报告"
    assert approval["payload"]["allowed_decisions"] == ["approve", "edit", "reject"]
    assert v3_sessions.get_pending_interrupt("t1") == "int-1"
    done = frames[-1]
    assert done["payload"]["awaiting_approval"] is True


async def test_custom_tool_progress_and_state_update():
    frames = await _collect([
        _custom({"activity-analysis": "tool_progress", "tool": "search_activities",
                 "status": "running", "args_summary": {"keyword": "贷款"}}),
        _custom({"activity-analysis": "tool_progress", "tool": "search_activities",
                 "status": "done", "summary": "3 条"}),
        _custom({"activity-analysis": "state_update", "data": {"activity_list": [{"activity_id": "A1"}]}}),
        _custom({"step": "marketing_report_synthesis", "status": "running"}),
        _out("answer", {"output": "ok", "result_type": "answer"}),
    ])
    types = [f["type"] for f in frames]
    assert types == ["node_update", "node_update", "node_update", "node_update", "done"]
    assert frames[0]["node"] == "search_activities"
    assert frames[0]["payload"]["tool_status"] == "running"
    assert frames[1]["payload"]["tool_status"] == "done"
    assert frames[2]["payload"]["activity_list"] == [{"activity_id": "A1"}]
    assert frames[3]["node"] == "marketing_report_synthesis"
    assert frames[-1]["payload"]["tool_calls_count"] == 1


async def test_cancel_emits_cancelled_frame():
    chunks = [_out("llm_output", {"content": "x", "result_type": "stream"})]

    class _CancelStream(_FakeRunnerStream):
        def __call__(self, agent, inputs, *, session=None, stream_modes=None):
            async def gen():
                yield self._chunks[0]
                yield self._chunks[0]  # 第二帧消费前 is_cancelled 已为真
            return gen()

    calls = {"n": 0}

    def is_cancelled():
        calls["n"] += 1
        return calls["n"] > 1

    monkeypatch_target = v3_bridge.Runner
    orig = monkeypatch_target.run_agent_streaming
    monkeypatch_target.run_agent_streaming = _CancelStream(chunks)
    try:
        frames = []
        async for f in v3_bridge.stream_v3_events(
                agent=None, session=None, inputs={"query": "hi"},
                request_id="r1", thread_id="t1", is_cancelled=is_cancelled):
            frames.append(_parse(f))
    finally:
        monkeypatch_target.run_agent_streaming = orig
    assert frames[-1]["type"] == "cancelled"


async def test_cancel_takes_effect_while_stream_blocked(monkeypatch):
    """长 LLM 调用期间流内无帧：取消须在轮询粒度内生效（泵+超时轮询设计）。

    联调实测：旧实现只在帧间隙检查取消，modify_report 单次 LLM 调用 2m38s
    期间点击停止无响应。
    """
    monkeypatch.setattr(v3_bridge, "_CANCEL_POLL_INTERVAL_S", 0.05)
    started = asyncio.get_running_loop().time()

    class _BlockedStream(_FakeRunnerStream):
        def __call__(self, agent, inputs, *, session=None, stream_modes=None):
            async def gen():
                yield self._chunks[0]
                await asyncio.sleep(60)  # 模拟工具内长 LLM 调用：之后再无帧
            return gen()

    flag = {"cancelled": False}

    def is_cancelled():
        return flag["cancelled"]

    orig = v3_bridge.Runner.run_agent_streaming
    v3_bridge.Runner.run_agent_streaming = _BlockedStream(
        [_out("llm_output", {"content": "x", "result_type": "stream"})])
    try:
        async def _cancel_soon():
            await asyncio.sleep(0.15)
            flag["cancelled"] = True

        task = asyncio.create_task(_cancel_soon())
        frames = []
        async for f in v3_bridge.stream_v3_events(
                agent=None, session=None, inputs={"query": "hi"},
                request_id="r1", thread_id="t1", is_cancelled=is_cancelled):
            frames.append(_parse(f))
        await task
    finally:
        v3_bridge.Runner.run_agent_streaming = orig

    elapsed = asyncio.get_running_loop().time() - started
    assert frames[-1]["type"] == "cancelled"
    assert elapsed < 5, f"取消后应及时返回，实际 {elapsed:.1f}s"
