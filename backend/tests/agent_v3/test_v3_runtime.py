"""agent_v3 runtime 测试：monkeypatch bridge/agent，验证审计、取消、resume 契约。"""

import json
from types import SimpleNamespace

import pytest

from src.agent_v3 import runtime as v3_runtime
from src.agent_v3 import sessions as v3_sessions
from src.services.agent_run_history_service import _original_user_text


def _parse(frame_text):
    line = frame_text.split("\n")[0]
    if line.startswith("id: "):
        line = frame_text.split("\n")[1]
    assert line.startswith("data: ")
    return json.loads(line[len("data: "):])


def setup_function():
    v3_sessions.reset_sessions()
    v3_runtime._cancelled.clear()
    v3_runtime._buffered_runs.clear()


@pytest.fixture
def fake_deps(monkeypatch):
    calls = {"turn_start": [], "turn_finish": []}
    monkeypatch.setattr(v3_runtime, "record_turn_start",
                        lambda s: calls["turn_start"].append(s))
    monkeypatch.setattr(v3_runtime, "finish_turn",
                        lambda *a, **k: calls["turn_finish"].append((a, k)))
    monkeypatch.setattr(v3_runtime, "get_v3_agent", _fake_agent)
    monkeypatch.setattr(v3_sessions, "create_agent_session",
                        lambda session_id=None, card=None: SimpleNamespace(
                            session_id=session_id, get_state=lambda k=None: None,
                            update_state=lambda d: None,
                            pre_run=lambda **kw: _async_noop()))
    return calls


async def _fake_agent():
    return SimpleNamespace(card=SimpleNamespace(id="fake-agent"))


async def _async_noop():
    return None


def _fake_stream(frames):
    async def gen(**kwargs):
        for f in frames:
            yield f
    return gen


async def test_run_bridge_error_marks_turn_failed(fake_deps, monkeypatch):
    """bridge 对框架吞掉的执行异常（answer result_type=error）抛 RuntimeError 时，
    runtime 必须给前端 error 帧并把 turn 记 failed——不能静默 success
    （静默 success + context 未落库 = 之后每轮都被当成第一个问题）。"""
    async def raising_stream(**kwargs):
        raise RuntimeError("LLM client 创建失败: verify_ssl")
        yield  # pragma: no cover - 使其成为异步生成器

    monkeypatch.setattr(v3_runtime, "stream_v3_events", raising_stream)
    frames = []
    async for f in v3_runtime.stream_agent_run(thread_id="t1", message="查询所有活动"):
        frames.append(f)
    assert _parse(frames[-1])["type"] == "error"
    assert "verify_ssl" in _parse(frames[-1])["payload"]["message"]
    status = fake_deps["turn_finish"][0][0][1]
    assert status == "failed"


async def test_run_emits_frames_and_audit(fake_deps, monkeypatch):
    monkeypatch.setattr(v3_runtime, "stream_v3_events",
                        lambda **kw: _fake_stream([
                            'data: {"type": "done", "payload": {}}\n\n'])())
    frames = []
    async for f in v3_runtime.stream_agent_run(thread_id="t1", message="你好"):
        frames.append(f)
    assert _parse(frames[-1])["type"] == "done"
    assert len(fake_deps["turn_start"]) == 1
    assert fake_deps["turn_start"][0]["thread_id"] == "t1"
    status = fake_deps["turn_finish"][0][0][1]
    assert status == "success"


async def test_run_turn_start_state_user_text_extractable_without_langchain(fake_deps, monkeypatch):
    """record_turn_start 的 state 不含 langchain 消息：messages 为 dict 列表，
    _original_user_text 必须能提取 user_text（以 agent_run_history_service 源码为准）。"""
    monkeypatch.setattr(v3_runtime, "stream_v3_events",
                        lambda **kw: _fake_stream([
                            'data: {"type": "done", "payload": {}}\n\n'])())
    frames = []
    async for f in v3_runtime.stream_agent_run(thread_id="t1", message="帮我分析活动"):
        frames.append(f)
    state = fake_deps["turn_start"][0]
    # v3 不应依赖 langchain 消息类型：messages 只能是 dict/基础类型
    for msg in state.get("messages") or []:
        assert isinstance(msg, dict)
    assert _original_user_text(state) == "帮我分析活动"


async def test_resume_without_pending_interrupt_errors(fake_deps):
    frames = []
    async for f in v3_runtime.stream_agent_resume(thread_id="t1", decision="approve"):
        frames.append(f)
    assert _parse(frames[-1])["type"] == "error"


async def test_resume_builds_interactive_input(fake_deps, monkeypatch):
    seen = {}

    async def spy_stream(agent, session, inputs, **kw):
        seen["inputs"] = inputs
        yield 'data: {"type": "done", "payload": {}}\n\n'

    monkeypatch.setattr(v3_runtime, "stream_v3_events", spy_stream)
    v3_sessions.set_pending_interrupt("t1", "int-9")
    frames = []
    async for f in v3_runtime.stream_agent_resume(
            thread_id="t1", decision="edit", tool="modify_report",
            edited_args={"free_instruction": "改"}):
        frames.append(f)
    ii = seen["inputs"]["query"]
    assert ii.user_inputs["int-9"]["decision"] == "edit"
    assert ii.user_inputs["int-9"]["edited_args"] == {"free_instruction": "改"}
    assert v3_sessions.get_pending_interrupt("t1") is None


async def test_resume_audit_state_extractable(fake_deps, monkeypatch):
    """resume 的审计 state：original_user_text 为 message 或审计文案，可提取。"""
    async def spy_stream(agent, session, inputs, **kw):
        yield 'data: {"type": "done", "payload": {}}\n\n'

    monkeypatch.setattr(v3_runtime, "stream_v3_events", spy_stream)
    v3_sessions.set_pending_interrupt("t1", "int-1")
    frames = []
    async for f in v3_runtime.stream_agent_resume(
            thread_id="t1", decision="reject", tool="generate_report"):
        frames.append(f)
    state = fake_deps["turn_start"][0]
    assert _original_user_text(state) == "已审批 generate_report：reject"


async def test_resume_rejects_bad_decision(fake_deps):
    frames = []
    async for f in v3_runtime.stream_agent_resume(thread_id="t1", decision="maybe"):
        frames.append(f)
    assert _parse(frames[-1])["type"] == "error"


def test_run_status_exposes_pending_approval():
    """run status 必须暴露服务端权威的待决审批状态：前端刷新后凭此
    作废本地残留的未决审批卡片（缓冲过期/进程重启后本地状态会失配）。"""
    assert v3_runtime.get_buffered_run_status("t-none")["pending_approval"] is False
    v3_sessions.set_pending_interrupt("t1", "int-1")
    try:
        status = v3_runtime.get_buffered_run_status("t1")
        assert status["pending_approval"] is True
        assert status["exists"] is False
    finally:
        v3_sessions.clear_pending_interrupt("t1")


async def test_duplicate_run_conflict(fake_deps, monkeypatch):
    async def slow_stream(**kw):
        import asyncio
        yield 'data: {"type": "node_update", "payload": {}}\n\n'
        await asyncio.sleep(5)

    monkeypatch.setattr(v3_runtime, "stream_v3_events", lambda **kw: slow_stream())
    s1 = await v3_runtime.start_buffered_agent_run(thread_id="t1", message="a")
    first = await s1.__anext__()
    assert _parse(first)["type"] == "node_update"
    s2 = await v3_runtime.start_buffered_agent_run(thread_id="t1", message="b")
    conflict = await s2.__anext__()
    assert _parse(conflict)["type"] == "error"
    v3_runtime.request_cancel("t1")


# ---- steer（任意时刻插话）----


async def test_steer_rejects_without_active_run(fake_deps):
    frames = []
    async for f in v3_runtime.stream_agent_steer(thread_id="t1", message="等等，换个方向"):
        frames.append(f)
    assert _parse(frames[-1])["type"] == "error"
    assert "没有正在运行的任务" in _parse(frames[-1])["payload"]["message"]


async def test_steer_rejects_when_pending_approval(fake_deps):
    """有待决审批时插话必须被拒绝：新 run 会清掉 /resume 正要恢复的现场。"""
    v3_sessions.set_pending_interrupt("t1", "int-1")
    try:
        frames = []
        async for f in v3_runtime.stream_agent_steer(thread_id="t1", message="换个方向"):
            frames.append(f)
        assert _parse(frames[-1])["type"] == "error"
        assert "等待审批" in _parse(frames[-1])["payload"]["message"]
    finally:
        v3_sessions.clear_pending_interrupt("t1")


async def test_steer_cancels_old_run_and_restarts_with_message(fake_deps, monkeypatch):
    """插话：旧 run 收到取消信号并释放注册表后，新 run 以插话为 user 消息启动。"""
    import asyncio

    old_cancel_event = asyncio.Event()
    v3_runtime._cancelled["t1"] = old_cancel_event

    async def fake_old_run_release():
        # 模拟旧 run 在取消信号后收尾（bridge 轮询粒度内）并释放注册表
        await old_cancel_event.wait()
        await asyncio.sleep(0.05)
        v3_runtime._cancelled.pop("t1", None)

    release_task = asyncio.create_task(fake_old_run_release())

    monkeypatch.setattr(v3_runtime, "stream_v3_events",
                        lambda **kw: _fake_stream([
                            'data: {"type": "done", "payload": {}}\n\n'])())
    frames = []
    try:
        async for f in v3_runtime.stream_agent_steer(
                thread_id="t1", message="把国庆预热活动也并进来"):
            frames.append(f)
    finally:
        release_task.cancel()

    assert old_cancel_event.is_set(), "steer 必须先取消旧 run"
    assert _parse(frames[-1])["type"] == "done"
    # 新 turn 以插话内容落审计，模型据此重新规划
    assert fake_deps["turn_start"][0]["thread_id"] == "t1"
    assert _original_user_text(fake_deps["turn_start"][0]) == "把国庆预热活动也并进来"
    assert fake_deps["turn_finish"][0][0][1] == "success"


async def test_steer_times_out_when_old_run_stuck():
    """旧 run 迟迟不释放注册表时，steer 必须超时报错而不是无限等待。"""
    import asyncio

    stuck_event = asyncio.Event()
    v3_runtime._cancelled["t1"] = stuck_event
    monkeypatch_timeout = v3_runtime._STEER_RELEASE_TIMEOUT_S
    v3_runtime._STEER_RELEASE_TIMEOUT_S = 0.2
    try:
        frames = []
        async for f in v3_runtime.stream_agent_steer(thread_id="t1", message="插话"):
            frames.append(f)
        assert _parse(frames[-1])["type"] == "error"
        assert "超时" in _parse(frames[-1])["payload"]["message"]
    finally:
        v3_runtime._STEER_RELEASE_TIMEOUT_S = monkeypatch_timeout
        v3_runtime._cancelled.clear()


async def test_start_buffered_run_replace_takes_over_slot():
    """replace=True：活跃 run 占用槽位时接管而不是返回冲突错误（steer 语义）。"""

    async def slow_source():
        import asyncio
        await asyncio.sleep(0.2)
        yield 'data: {"type": "node_update", "payload": {}}\n\n'

    s1 = await v3_runtime._start_buffered_run("t1", slow_source())
    s2 = await v3_runtime._start_buffered_run(
        "t1", _fake_stream(['data: {"type": "done", "payload": {}}\n\n'])(),
        replace=True,
    )
    first = await s2.__anext__()
    assert _parse(first)["type"] == "done"
    await s1.aclose()
    await s2.aclose()


async def test_fresh_run_detaches_cancelled_context_pool(fake_deps, monkeypatch):
    """被 aclose 取消的 run 其 stream_process 仍在后台续跑并往共享池追加消息；
    新 run 必须把池内上下文摘除成 sanitized 快照注入 session state，否则双方
    交错追加把历史搅成 OpenAI 400（tool_calls 与 tool 结果不配对）。"""

    class _FakeContext:
        def __init__(self, messages):
            self._messages = messages
            self.get_calls = []

        def session_id(self):
            return "t1"

        def context_id(self):
            return "default_context_id"

        def get_messages(self, with_history=False):
            self.get_calls.append(with_history)
            return list(self._messages)

        def set_messages(self, messages, with_history=False):
            self._messages = messages

    def _fake_sanitize(messages):
        # 最小版框架语义：丢弃带 tool_calls 的 assistant（悬空块）
        return [m for m in messages if not getattr(m, "tool_calls", None)]

    dangling = SimpleNamespace(
        role="assistant", content="我来生成报告",
        tool_calls=[SimpleNamespace(id="call_1")], tool_call_id=None,
    )
    user_msg = SimpleNamespace(role="user", content="生成报告",
                               tool_calls=None, tool_call_id=None)
    context = _FakeContext([user_msg, dangling])
    engine = SimpleNamespace(_context_pool={"t1_default_context_id": context})

    async def _agent_fn():
        return SimpleNamespace(
            card=SimpleNamespace(id="fake-agent"),
            context_engine=engine,
            _sanitize_cancelled_turn_messages=staticmethod(_fake_sanitize),
        )
    monkeypatch.setattr(v3_runtime, "get_v3_agent", _agent_fn)

    state_updates = []

    def _fake_session(session_id=None, card=None):
        return SimpleNamespace(
            session_id=session_id,
            get_state=lambda k=None: None,
            update_state=lambda d: state_updates.append(d),
            pre_run=lambda **kw: _async_noop(),
        )
    monkeypatch.setattr(v3_sessions, "create_agent_session", _fake_session)
    monkeypatch.setattr(v3_runtime, "stream_v3_events",
                        lambda **kw: _fake_stream([
                            'data: {"type": "done", "payload": {}}\n\n'])())

    frames = []
    async for f in v3_runtime.stream_agent_run(thread_id="t1", message="换红色色调"):
        frames.append(f)

    assert _parse(frames[-1])["type"] == "done"
    # 池子已被摘除：旧 run 后台续跑只污染它自己持有的旧对象
    assert engine._context_pool == {}
    # 快照必须取全量（含 history 前缀）——rebulid 会把恢复的消息标为 history，
    # 第二次插话时若只取尾部会丢掉全部真实历史
    assert context.get_calls and all(flag is True for flag in context.get_calls)
    # 干净快照经 session state 注入新 run（悬空 assistant 被清理）
    injected = state_updates[-1]["context"]
    assert injected["default_context_id"]["messages"] == [user_msg]
