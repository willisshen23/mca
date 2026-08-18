"""agent_v3 会话注册表测试（不触真实 openjiuwen，monkeypatch create_agent_session）。"""

from src.agent_v3 import sessions


class _FakeState:
    def __init__(self):
        self._data = {}

    def get_global(self, key):
        return self._data.get(key)

    def update_global(self, data):
        self._data.update(data)


class _FakeSession:
    """模拟 openjiuwen.core.session.agent.Session 的 get_state/update_state。"""

    def __init__(self, session_id):
        self.session_id = session_id
        self._state = _FakeState()

    def get_state(self, key=None):
        return self._state.get_global(key)

    def update_state(self, data):
        self._state.update_global(data)


def setup_function():
    sessions.reset_sessions()


def test_new_run_session_creates_fresh_instance_each_time(monkeypatch):
    """每轮 run 新建实例（框架设计：post_run 会关闭流，实例一次性）。"""
    monkeypatch.setattr(sessions, "create_agent_session", lambda session_id=None, card=None: _FakeSession(session_id))
    a = sessions.new_run_session("t1", card="dummy")
    b = sessions.new_run_session("t1", card="dummy")
    assert a is not b
    c = sessions.new_run_session("t2", card="dummy")
    assert c.session_id == "t2"


def test_pending_interrupt_cycle(monkeypatch):
    monkeypatch.setattr(sessions, "create_agent_session", lambda session_id=None, card=None: _FakeSession(session_id))
    assert sessions.get_pending_interrupt("t1") is None
    sessions.set_pending_interrupt("t1", "int-1")
    assert sessions.get_pending_interrupt("t1") == "int-1"
    sessions.clear_pending_interrupt("t1")
    assert sessions.get_pending_interrupt("t1") is None


def test_read_business_state_defaults_without_session():
    state = sessions.read_business_state("nonexistent")
    assert state == {
        "html_report": "",
        "analysis_queue": [],
        "report_context": {},
        "activity_list": [],
        "formatted_output_path": "",
    }


def test_read_business_state_reads_latest_session(monkeypatch):
    monkeypatch.setattr(sessions, "create_agent_session", lambda session_id=None, card=None: _FakeSession(session_id))
    sessions.new_run_session("t1", card="dummy")
    latest = sessions.new_run_session("t1", card="dummy")
    latest.update_state({"html_report": "<html>x</html>", "analysis_queue": [{"activity_id": "A1"}]})
    state = sessions.read_business_state("t1")
    assert state["html_report"] == "<html>x</html>"
    assert state["analysis_queue"] == [{"activity_id": "A1"}]
    assert state["report_context"] == {}


def test_create_without_card_raises():
    import pytest

    with pytest.raises(ValueError, match="card"):
        sessions.new_run_session("t-no-card")


async def test_real_session_state_restored_across_runs():
    """回归：① create_agent_session 必须带 card（否则 pre_run 报 NoneType.id）；
    ② 每轮新建实例时，状态经 in-memory checkpointer 按 session_id 恢复
    （不能复用实例——post_run 关闭流后复用报 StreamQueue is already closed）。

    本测试不打桩 create_agent_session，直接走真实 openjiuwen 对象（离线）。
    """
    from openjiuwen.core.single_agent import AgentCard

    card = AgentCard(id="regression-agent", description="regression")
    s1 = sessions.new_run_session("t-real", card=card)
    await s1.pre_run(inputs={"query": "hi"})
    s1.update_state({"analysis_queue": [{"activity_id": "A1"}]})
    await s1.post_run()  # commit + 关闭流

    # 第二轮：新实例、同 thread_id，状态应恢复
    s2 = sessions.new_run_session("t-real", card=card)
    assert s2 is not s1
    await s2.pre_run(inputs={"query": "again"})
    assert s2.get_state("analysis_queue") == [{"activity_id": "A1"}]
