from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from src.infrastructure.db.models import Base, LlmTokenUsageLog


@pytest.fixture()
def engine():
    db_engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(db_engine)
    try:
        yield db_engine
    finally:
        Base.metadata.drop_all(db_engine)
        db_engine.dispose()


def test_llm_token_usage_log_applies_defaults(engine):
    with Session(engine) as session:
        usage = LlmTokenUsageLog(
            id="019fab7f-2c13-7f60-b526-88fc6097ff71",
            time_spent=1250,
            token_cost=2048,
            exec_status="SUCCESS",
        )
        session.add(usage)
        session.commit()

        saved = session.scalar(select(LlmTokenUsageLog))

    assert saved is not None
    assert saved.etl_dt == date.today()
    assert saved.agent_id == "rtl-ActivityReport"
    assert saved.name == "活动分析助手"
    assert isinstance(saved.start_time, datetime)


def test_llm_token_usage_mysql_ddl_uses_compatible_date_defaults():
    ddl = str(
        CreateTable(LlmTokenUsageLog.__table__).compile(dialect=mysql.dialect())
    )

    assert "DEFAULT CURRENT_DATE" not in ddl
    assert "DEFAULT (CURRENT_DATE)" not in ddl
    assert "DEFAULT (now())" not in ddl
    assert "DEFAULT 'CURRENT_TIMESTAMP'" not in ddl
    assert "DEFAULT CURRENT_TIMESTAMP" in ddl


@pytest.mark.parametrize(
    ("time_spent", "token_cost", "exec_status"),
    [
        (-1, 1, "SUCCESS"),
        (1, -1, "SUCCESS"),
        (1, 1, "success"),
    ],
)
def test_llm_token_usage_log_rejects_invalid_metrics(
    engine,
    time_spent,
    token_cost,
    exec_status,
):
    with Session(engine) as session:
        session.add(
            LlmTokenUsageLog(
                id=f"invalid-{time_spent}-{token_cost}-{exec_status}",
                time_spent=time_spent,
                token_cost=token_cost,
                exec_status=exec_status,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
