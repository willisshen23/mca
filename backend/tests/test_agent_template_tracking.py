from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.infrastructure.db.models import ActivityAnalysisTemplate, AgentRunHistory, Base
from src.infrastructure.db.session import get_db
from src.main import app
from src.services import activity_template_service
from src.services import agent_run_history_service
from src.services.activity_template_service import (
    get_template_by_code,
    increment_template_usage_by_code,
)
from src.services.agent_run_history_service import ensure_report_run_history, record_template_match

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def db(monkeypatch):
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(agent_run_history_service, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(activity_template_service, "SessionLocal", TestingSessionLocal)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def history_row(db):
    row = AgentRunHistory(
        request_id="req-001",
        thread_id="thread-001",
        started_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def activity_template(db):
    template = ActivityAnalysisTemplate(
        code="tpl_test_001",
        name="测试分析模板",
        type="线上活动",
        description="测试描述",
        skills_json='["skill_a"]',
        icon="ti-test",
        color="#165DFF",
        bg="#E8F0FF",
        use_count=0,
        status="active",
        is_builtin=False,
    )
    db.add(template)
    db.commit()
    return template


def test_record_template_match_updates_history(db, history_row, activity_template):
    record_template_match("req-001", activity_template, "测试数据模板")

    db.refresh(history_row)
    assert history_row.matched_data_template_name == "测试数据模板"
    assert history_row.activity_template_snapshot is not None
    assert history_row.activity_template_snapshot["code"] == "tpl_test_001"
    assert history_row.activity_template_snapshot["name"] == "测试分析模板"
    assert history_row.activity_template_snapshot["type"] == "线上活动"
    assert history_row.activity_template_snapshot["description"] == "测试描述"
    assert history_row.activity_template_snapshot["skills_json"] == '["skill_a"]'
    assert history_row.activity_template_snapshot["icon"] == "ti-test"
    assert history_row.activity_template_snapshot["color"] == "#165DFF"
    assert history_row.activity_template_snapshot["bg"] == "#E8F0FF"
    assert history_row.activity_template_snapshot["status"] == "active"
    assert history_row.activity_template_snapshot["is_builtin"] is False


def test_record_template_match_overwrites_on_same_request_id(db, history_row, activity_template):
    record_template_match("req-001", activity_template, "第一次")
    record_template_match("req-001", activity_template, "第二次")

    db.refresh(history_row)
    assert history_row.matched_data_template_name == "第二次"


def test_record_template_match_skips_missing_request_id(activity_template):
    record_template_match("", activity_template, "数据模板")  # should not raise


def test_record_template_match_skips_missing_row(activity_template):
    record_template_match("non-existent", activity_template, "数据模板")  # should not raise


def test_ensure_report_run_history_creates_row(db):
    ensure_report_run_history("req-ensure-001", "thread-ensure-001")

    row = db.query(AgentRunHistory).filter(AgentRunHistory.request_id == "req-ensure-001").first()
    assert row is not None
    assert row.thread_id == "thread-ensure-001"
    assert row.started_at is not None


def test_ensure_report_run_history_does_not_overwrite_existing_row(db):
    existing = AgentRunHistory(
        request_id="req-ensure-002",
        thread_id="thread-original",
        started_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    db.add(existing)
    db.commit()

    ensure_report_run_history("req-ensure-002", "thread-new")

    db.refresh(existing)
    assert existing.thread_id == "thread-original"
    assert existing.started_at is not None
    assert existing.started_at.year == 2020
    assert existing.started_at.month == 1
    assert existing.started_at.day == 1


def test_ensure_report_run_history_skips_missing_request_id(db):
    # Should not raise or create anything.
    ensure_report_run_history("", "thread-001")
    assert db.query(AgentRunHistory).count() == 0


def test_record_template_match_after_ensure_saves_snapshot(db, activity_template):
    ensure_report_run_history("req-003", "thread-003")
    record_template_match("req-003", activity_template, "数据模板")

    row = db.query(AgentRunHistory).filter(AgentRunHistory.request_id == "req-003").first()
    assert row is not None
    assert row.activity_template_snapshot is not None
    assert row.matched_data_template_name == "数据模板"


def test_increment_template_usage_by_code(db, activity_template):
    result = increment_template_usage_by_code("tpl_test_001")
    assert result is not None
    assert result.use_count == 1

    db.refresh(activity_template)
    assert activity_template.use_count == 1


def test_increment_template_usage_by_code_returns_none_for_missing_code(db):
    assert increment_template_usage_by_code("missing") is None


def test_get_template_by_code(db, activity_template):
    found = get_template_by_code(db, "tpl_test_001")
    assert found is not None
    assert found.name == "测试分析模板"


def test_get_template_by_code_returns_none_for_missing(db):
    assert get_template_by_code(db, "missing") is None


def test_agent_run_history_schema_upgrade_adds_tracking_columns():
    # Create a fresh in-memory engine and simulate the old schema (without tracking columns).
    upgrade_engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=upgrade_engine)
    with upgrade_engine.begin() as conn:
        conn.execute(text("ALTER TABLE agent_run_history DROP COLUMN activity_template_snapshot"))
        conn.execute(text("ALTER TABLE agent_run_history DROP COLUMN matched_data_template_name"))

    original_engine = agent_run_history_service.engine
    agent_run_history_service.engine = upgrade_engine
    try:
        agent_run_history_service.ensure_agent_run_history_schema()
    finally:
        agent_run_history_service.engine = original_engine

    inspector = inspect(upgrade_engine)
    columns = {column["name"] for column in inspector.get_columns("agent_run_history")}
    assert "activity_template_snapshot" in columns
    assert "matched_data_template_name" in columns
