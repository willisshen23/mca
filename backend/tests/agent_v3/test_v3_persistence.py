"""agent_v3 持久化 checkpointer（P2）测试。

覆盖：
- init_v3_checkpointer 的 conf 正确性（monkeypatch factory，不落盘）；
- 关键离线集成：真实 PersistenceCheckpointer + 临时 SQLite 文件——
  保存后抛弃实例，用全新 checkpointer + 全新同 thread_id 会话恢复，
  断言业务键恢复（模拟进程重启续聊）；
- delete_v3_thread_checkpoint：按键前缀清理，文件/表不存在静默跳过。
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest
from openjiuwen.core.session.agent import create_agent_session
from openjiuwen.core.session.checkpointer import CheckpointerFactory
from openjiuwen.core.session.checkpointer.checkpointer import CheckpointerConfig
from openjiuwen.core.single_agent import AgentCard

import src.agent_v3.state.persistence as persistence


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    monkeypatch.setattr(persistence, "_checkpointer", None)
    yield
    monkeypatch.setattr(persistence, "_checkpointer", None)


def _fake_settings(db_path: str):
    return SimpleNamespace(agent_v3_checkpointer_db_path=db_path)


async def test_init_v3_checkpointer_conf(monkeypatch, tmp_path):
    """conf 必须走 SQLite + WAL + 5s 锁超时，并设为框架全局默认。"""
    db_path = tmp_path / "v3_checkpoints.db"
    monkeypatch.setattr(persistence, "get_settings",
                        lambda: _fake_settings(str(db_path)))

    captured: dict = {}

    async def fake_create(config):
        captured["config"] = config
        return "fake-checkpointer"

    monkeypatch.setattr(CheckpointerFactory, "create", fake_create)
    monkeypatch.setattr(
        CheckpointerFactory, "set_default_checkpointer",
        staticmethod(lambda cp: captured.setdefault("default", cp)),
    )

    await persistence.init_v3_checkpointer()

    config = captured["config"]
    assert isinstance(config, CheckpointerConfig)
    assert config.type == "persistence"
    assert config.conf == {
        "db_type": "sqlite",
        "db_path": str(db_path),
        "db_timeout": 5,
        "db_enable_wal": True,
    }
    assert captured["default"] == "fake-checkpointer"

    # 幂等：二次调用不再创建
    await persistence.init_v3_checkpointer()
    assert captured["config"] is config


async def test_persistence_checkpointer_save_and_recover_across_instances(tmp_path):
    """模拟进程重启：实例 A 保存 → 全新 checkpointer B + 全新会话恢复。"""
    db_path = tmp_path / "v3_checkpoints.db"
    card = AgentCard(id="test-agent", description="t")
    conf = CheckpointerConfig(
        type="persistence",
        conf={"db_type": "sqlite", "db_path": str(db_path)},
    )

    checkpointer_a = await CheckpointerFactory.create(conf)
    session_a = create_agent_session(session_id="thread-1", card=card)
    session_a.update_state({
        "html_report": "<html>报告v1</html>",
        "analysis_queue": [{"activity_id": "A01"}],
    })
    await checkpointer_a.post_agent_execute(session_a._inner)
    assert db_path.exists(), "checkpoint 必须落盘到独立 SQLite 文件"

    # 进程重启语义：checkpointer 与会话都是全新实例，仅 thread_id 相同
    checkpointer_b = await CheckpointerFactory.create(conf)
    session_b = create_agent_session(session_id="thread-1", card=card)
    await checkpointer_b.pre_agent_execute(session_b._inner, None)

    assert session_b.get_state("html_report") == "<html>报告v1</html>"
    assert session_b.get_state("analysis_queue") == [{"activity_id": "A01"}]

    # 其他 thread 无状态可恢复（全新起步，不抛错）
    session_c = create_agent_session(session_id="thread-2", card=card)
    await checkpointer_b.pre_agent_execute(session_c._inner, None)
    assert session_c.get_state("html_report") is None


async def test_delete_v3_thread_checkpoint(monkeypatch, tmp_path):
    """按键前缀清理目标 thread，其他 thread 的键不受影响。"""
    db_path = tmp_path / "v3_checkpoints.db"
    monkeypatch.setattr(persistence, "get_settings",
                        lambda: _fake_settings(str(db_path)))

    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE kv_store (key VARCHAR(255) PRIMARY KEY, value VARCHAR(4096) NOT NULL)")
    conn.executemany(
        "INSERT INTO kv_store (key, value) VALUES (?, ?)",
        [
            ("t1:agent:a1:agent_state_blobs", "x"),
            ("t1:agent:a1:agent_state_blobs_dump_type", "pickle"),
            ("t2:agent:a1:agent_state_blobs", "y"),
        ],
    )
    conn.commit()
    conn.close()

    await persistence.delete_v3_thread_checkpoint("t1")

    conn = sqlite3.connect(db_path)
    keys = [row[0] for row in conn.execute("SELECT key FROM kv_store")]
    conn.close()
    assert keys == ["t2:agent:a1:agent_state_blobs"]


async def test_delete_v3_thread_checkpoint_silent_when_missing(monkeypatch, tmp_path):
    """文件不存在、表不存在、空 thread_id 都必须静默跳过。"""
    # 文件不存在
    missing = tmp_path / "nope.db"
    monkeypatch.setattr(persistence, "get_settings",
                        lambda: _fake_settings(str(missing)))
    await persistence.delete_v3_thread_checkpoint("t1")

    # 文件存在但 kv_store 表不存在（从未写入 checkpoint）
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    monkeypatch.setattr(persistence, "get_settings",
                        lambda: _fake_settings(str(empty)))
    await persistence.delete_v3_thread_checkpoint("t1")

    # 空 thread_id
    await persistence.delete_v3_thread_checkpoint("")


async def test_prepare_fresh_run_session(tmp_path):
    """审批挂起跨重启：checkpoint 残留 __react_agent_interruption__ 时，
    prepare_fresh_run_session 提前 recover、作废残留并修补悬空 tool_call。"""
    from openjiuwen.core.single_agent.interrupt.state import INTERRUPTION_KEY

    from src.agent_v3 import sessions as v3_sessions

    db_path = tmp_path / "v3_checkpoints.db"
    card = AgentCard(id="test-agent", description="t")
    conf = CheckpointerConfig(
        type="persistence",
        conf={"db_type": "sqlite", "db_path": str(db_path)},
    )

    # 模拟"审批挂起时进程退出"：checkpoint 里带中断现场 + 悬空 tool_call
    # （assistant 消息带 tool_calls 但无 tool 结果——中断发生在工具执行前）
    from openjiuwen.core.foundation.llm import AssistantMessage, ToolCall

    dangling = AssistantMessage(
        content="我将把活动加入分析队列。",
        tool_calls=[ToolCall(id="call_1", type="function",
                             name="add_to_analysis_queue", arguments="{}")],
    )
    checkpointer_a = await CheckpointerFactory.create(conf)
    session_a = create_agent_session(session_id="thread-1", card=card)
    session_a.update_state({
        INTERRUPTION_KEY: {"iteration": 1},
        "html_report": "r",
        "context": {"default": {"messages": [
            {"role": "user", "content": "加入队列"},
            dangling,
        ]}},
    })
    await checkpointer_a.post_agent_execute(session_a._inner)

    # 模拟重启：全新 checkpointer + 全新会话，pre_run recover 后残留被作废
    checkpointer_b = await CheckpointerFactory.create(conf)
    CheckpointerFactory.set_default_checkpointer(checkpointer_b)
    try:
        session_b = create_agent_session(session_id="thread-1", card=card)
        discarded, repaired = await v3_sessions.prepare_fresh_run_session(
            session_b, inputs={"query": "新消息"})
        assert discarded is True
        assert repaired == 1
        assert session_b.get_state(INTERRUPTION_KEY) is None
        # 业务键不受影响
        assert session_b.get_state("html_report") == "r"
        # 悬空 tool_call 已被合成 tool 消息修补（紧随归属 assistant 消息）
        messages = session_b.get_state("context")["default"]["messages"]
        assert [getattr(m, "role", None) for m in messages[-2:]] == ["assistant", "tool"]
        assert messages[-1].tool_call_id == "call_1"
        assert "作废" in messages[-1].content
        # 生产路径上 run 完成会 post_run 落盘；这里模拟落盘后再验证
        await checkpointer_b.post_agent_execute(session_b._inner)

        # 残留已清、修补已落盘：再次 prepare 均为零
        session_c = create_agent_session(session_id="thread-1", card=card)
        assert await v3_sessions.prepare_fresh_run_session(session_c) == (False, 0)
    finally:
        CheckpointerFactory.set_default_checkpointer(None)
