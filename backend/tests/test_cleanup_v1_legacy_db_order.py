"""Regression test: cleanup_v1_data must not run before legacy databases
gain the newer agent_run_history columns.

Production failure (2026-07-24): on a legacy SQLite database missing
agent_run_history.activity_template_snapshot, startup crashed inside
cleanup_v1_data because its ORM query SELECTs every mapped column, and the
column-adding migration (ensure_agent_run_history_schema) only ran after it.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.infrastructure.db.models import (
    Base,
    ConversationMeta,
)
from src.infrastructure.db.migrations import cleanup_v1_data

# Legacy agent_run_history layout: everything except the tracking columns
# added later (activity_template_snapshot, matched_data_template_name).
_LEGACY_AGENT_RUN_HISTORY_DDL = """
CREATE TABLE agent_run_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id VARCHAR(64) NOT NULL,
    thread_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64),
    user_name VARCHAR(120),
    user_text TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    failure_reason TEXT,
    final_response TEXT,
    prompt_text TEXT,
    report_file_path TEXT,
    report_file_name VARCHAR(255),
    report_asset_name VARCHAR(255),
    report_asset_media_type VARCHAR(120),
    report_asset_blob BLOB,
    report_feedback VARCHAR(16),
    feedback_user_id VARCHAR(64),
    feedback_at DATETIME,
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    created_at DATETIME,
    updated_at DATETIME
)
"""


def _make_legacy_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE agent_run_history"))
        conn.execute(text(_LEGACY_AGENT_RUN_HISTORY_DDL))
    return engine


def _seed_v1_conversation(engine):
    Session = sessionmaker(bind=engine)
    with Session() as s:
        s.add(
            ConversationMeta(
                thread_id="t-v1",
                user_id="u1",
                title="v1 conversation",
                agent_version="v1",
            )
        )
        s.commit()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agent_run_history (request_id, thread_id, status, started_at) "
                "VALUES ('r1', 't-v1', 'success', :started_at)"
            ),
            {"started_at": datetime.now(timezone.utc)},
        )


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    from src.config import resolve_path as original_resolve_path

    monkeypatch.setattr(
        "src.config.resolve_path",
        lambda p: tmp_path if p == "data/backups" else original_resolve_path(p),
    )
    return tmp_path


def test_cleanup_v1_data_crashes_on_legacy_db_without_column_migration(backup_dir):
    """Documents the root cause: cleanup before the column migration fails."""
    engine = _make_legacy_engine()
    _seed_v1_conversation(engine)

    with pytest.raises(OperationalError, match="activity_template_snapshot"):
        asyncio.run(cleanup_v1_data(engine))


def test_legacy_db_startup_order_migrate_columns_then_cleanup(backup_dir, monkeypatch):
    """The fixed startup order: add missing columns first, then clean up."""
    engine = _make_legacy_engine()
    _seed_v1_conversation(engine)

    monkeypatch.setattr("src.services.agent_run_history_service.engine", engine)
    from src.services.agent_run_history_service import (
        ensure_agent_run_history_schema,
    )

    ensure_agent_run_history_schema()
    asyncio.run(cleanup_v1_data(engine))

    columns = {c["name"] for c in inspect(engine).get_columns("agent_run_history")}
    assert "activity_template_snapshot" in columns
    assert "matched_data_template_name" in columns
    assert "duration_ms" in columns
    assert "latest_version_no" in columns

    Session = sessionmaker(bind=engine)
    with Session() as s:
        assert s.query(ConversationMeta).filter_by(thread_id="t-v1").first() is None

    backup_files = list(backup_dir.glob("v1_cleanup_*.json"))
    assert len(backup_files) == 1
    data = json.loads(backup_files[0].read_text(encoding="utf-8"))
    assert data["thread_ids"] == ["t-v1"]
