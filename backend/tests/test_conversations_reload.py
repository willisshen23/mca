"""P2 会话重载（业务表驱动）测试。

GET /conversations/{id} 不再读任何 checkpoint（v2/v3 通吃）：
- messages 由 conversation_turn 全量轮次重建；
- html_report 取 report_versions 最新版本 HTML 本体；
- report_context / runtime_trace 降级为空（字段保留，前端容错）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.services.agent_run_history_service as history_svc
import src.services.conversation_log_service as log_svc
from src.api.routers.conversations import (
    _messages_from_turns,
    get_conversation,
)
from src.infrastructure.db.models import (
    AgentRunHistory,
    Base,
    ConversationMeta,
    ConversationTurn,
    ReportVersion,
)
from src.services.agent_run_history_service import (
    build_report_asset_html,
    get_latest_report_html_by_thread,
)

UTC = timezone.utc
_BASE = datetime(2026, 8, 9, 8, 0, 0, tzinfo=UTC)


@pytest.fixture
def Session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    monkeypatch.setattr(history_svc, "SessionLocal", session_factory)
    monkeypatch.setattr(log_svc, "SessionLocal", session_factory)
    return session_factory


def _add_turn(Session, request_id, thread_id, user_text, *, status="success",
              assistant_response=None, started_at):
    with Session() as s:
        s.add(
            ConversationTurn(
                request_id=request_id,
                thread_id=thread_id,
                user_id="u1",
                user_text=user_text,
                status=status,
                assistant_response=assistant_response,
                started_at=started_at,
            )
        )
        s.commit()


def _add_report(Session, request_id="r1", thread_id="t1",
                html="<html><body>活动分析报告</body></html>"):
    with Session() as s:
        s.add(
            AgentRunHistory(
                request_id=request_id,
                thread_id=thread_id,
                user_id="u1",
                user_text="生成分析报告",
                prompt_text="生成分析报告",
                status="success",
                started_at=_BASE,
                latest_version_no=1,
            )
        )
        s.add(
            ReportVersion(
                request_id=request_id,
                version_no=1,
                report_asset_name="report.html",
                report_asset_media_type="text/html; charset=utf-8",
                report_asset_blob=build_report_asset_html(html),
                source="generate",
            )
        )
        s.commit()


def test_messages_from_turns_filters_and_orders():
    turns = [
        # 正常轮：user + ai
        {"user_text": "查一下活动", "assistant_response": "共 3 个活动", "status": "success"},
        # 审批审计轮：整体丢弃
        {"user_text": "已审批 modify_report：approve", "assistant_response": "已修改", "status": "success"},
        # 失败且无回复：整体丢弃
        {"user_text": "再来一次", "assistant_response": "", "status": "failed"},
        # 审批挂起轮：只有用户消息
        {"user_text": "修改报告标题", "assistant_response": "", "status": "awaiting_approval"},
    ]
    assert _messages_from_turns(turns) == [
        {"role": "user", "content": "查一下活动"},
        {"role": "ai", "content": "共 3 个活动"},
        {"role": "user", "content": "修改报告标题"},
    ]


def test_get_latest_report_html_by_thread(Session):
    _add_report(Session)
    html = get_latest_report_html_by_thread("t1")
    assert "活动分析报告" in html
    # 无报告 / 空 thread 返回空串
    assert get_latest_report_html_by_thread("t-none") == ""
    assert get_latest_report_html_by_thread("") == ""


def test_get_conversation_reload_from_business_tables(Session):
    _add_turn(Session, "r1", "t1", "查一下活动",
              assistant_response="共 3 个活动", started_at=_BASE)
    _add_turn(Session, "r2", "t1", "已审批 modify_report：approve",
              assistant_response="已修改", started_at=_BASE + timedelta(minutes=1))
    _add_turn(Session, "r3", "t1", "生成报告",
              assistant_response="报告已生成", started_at=_BASE + timedelta(minutes=2))
    _add_report(Session, request_id="r3")
    with Session() as s:
        s.add(ConversationMeta(thread_id="t1", user_id="u1", title="分析对话"))
        s.commit()

    with Session() as db:
        detail = asyncio.run(get_conversation("t1", db=db, user_id="u1"))

    assert detail["messages"] == [
        {"role": "user", "content": "查一下活动"},
        {"role": "ai", "content": "共 3 个活动"},
        {"role": "user", "content": "生成报告"},
        {"role": "ai", "content": "报告已生成"},
    ]
    assert "活动分析报告" in detail["html_report"]
    assert detail["report_context"] == {}
    assert detail["runtime_trace"] == {}
    assert detail["report_history"] is not None
    assert isinstance(detail["report_histories"], list)
    assert detail["title"] == "分析对话"


def test_get_conversation_reload_empty_thread(Session):
    """业务表无记录但 meta 存在（极老会话）：消息/报告为空，不报错。"""
    with Session() as s:
        s.add(ConversationMeta(thread_id="t-old", user_id="u1", title="老会话"))
        s.commit()

    with Session() as db:
        detail = asyncio.run(get_conversation("t-old", db=db, user_id="u1"))

    assert detail["messages"] == []
    assert detail["html_report"] == ""
    assert detail["report_history"] is None
    assert detail["report_histories"] == []
    assert detail["report_placements"] == []
