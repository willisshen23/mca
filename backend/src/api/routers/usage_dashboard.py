from __future__ import annotations

import io
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, distinct, func
from sqlalchemy.orm import Session

from src.infrastructure.db.models import (
    AgentRunHistory,
    ConversationMeta,
    ConversationTurn,
    LlmTokenUsageLog,
    ReportVersion,
    UsageEvent,
)
from src.infrastructure.db.session import get_db
from src.services.usage_export_service import export_usage_details_xlsx

router = APIRouter(prefix="/usage-dashboard", tags=["usage-dashboard"])

ALLOWED_EVENTS = {"home_view"}
ALLOWED_PERIODS = {7, 30, 90}


class UsageEventRequest(BaseModel):
    event_type: str = Field(max_length=40)
    org_no: str | None = Field(default=None, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    path: str | None = Field(default=None, max_length=255)
    source: str | None = Field(default=None, max_length=80)
    referrer: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] | None = None


def _now() -> datetime:
    # Databases in this project store UTC as a timezone-naive DATETIME.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _pct_change(current: int, previous: int) -> float | None:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round((current - previous) * 100 / previous, 1)


def _count_in_period(
    db: Session,
    column,
    start: datetime,
    end: datetime,
    *,
    distinct_column=None,
    filters: tuple = (),
) -> int:
    target = func.count(distinct(distinct_column)) if distinct_column is not None else func.count()
    query = db.query(target).filter(column >= start, column < end, *filters)
    return int(query.scalar() or 0)


def _metric(
    db: Session,
    *,
    column,
    start: datetime,
    end: datetime,
    previous_start: datetime,
    distinct_column=None,
    filters: tuple = (),
) -> dict[str, int | float | None]:
    current = _count_in_period(
        db,
        column,
        start,
        end,
        distinct_column=distinct_column,
        filters=filters,
    )
    previous = _count_in_period(
        db,
        column,
        previous_start,
        start,
        distinct_column=distinct_column,
        filters=filters,
    )
    return {"value": current, "previous": previous, "change_pct": _pct_change(current, previous)}


def _sum_metric(
    db: Session,
    *,
    column,
    timestamp_column,
    start: datetime,
    end: datetime,
    previous_start: datetime,
) -> dict[str, int | float | None]:
    def total(period_start: datetime, period_end: datetime) -> int:
        value = (
            db.query(func.sum(column))
            .filter(timestamp_column >= period_start, timestamp_column < period_end)
            .scalar()
        )
        return int(value or 0)

    current = total(start, end)
    previous = total(previous_start, start)
    return {"value": current, "previous": previous, "change_pct": _pct_change(current, previous)}


def _daily_counts(
    db: Session,
    model,
    timestamp_column,
    start: datetime,
    end: datetime,
    *,
    filters: tuple = (),
    distinct_column=None,
) -> dict[str, int]:
    day = func.date(timestamp_column)
    target = func.count(distinct(distinct_column)) if distinct_column is not None else func.count()
    rows = (
        db.query(day, target)
        .select_from(model)
        .filter(timestamp_column >= start, timestamp_column < end, *filters)
        .group_by(day)
        .all()
    )
    return {str(row[0]): int(row[1] or 0) for row in rows}


def _daily_sums(
    db: Session,
    model,
    timestamp_column,
    value_column,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    day = func.date(timestamp_column)
    rows = (
        db.query(day, func.sum(value_column))
        .select_from(model)
        .filter(timestamp_column >= start, timestamp_column < end)
        .group_by(day)
        .all()
    )
    return {str(row[0]): int(row[1] or 0) for row in rows}


@router.post("/events", status_code=201)
def record_usage_event(
    body: UsageEventRequest,
    db: Session = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    event_type = body.event_type.strip().lower()
    if event_type not in ALLOWED_EVENTS:
        raise HTTPException(status_code=422, detail="Unsupported usage event")
    user_id = str(x_user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-Id")
    metadata_json = (
        json.dumps(body.metadata, ensure_ascii=False, separators=(",", ":"))
        if body.metadata
        else None
    )
    if metadata_json and len(metadata_json) > 4000:
        raise HTTPException(status_code=422, detail="metadata is too large")

    db.add(
        UsageEvent(
            event_type=event_type,
            user_id=user_id[:64],
            org_no=(body.org_no or "").strip()[:64] or None,
            session_id=(body.session_id or "").strip()[:64] or None,
            path=(body.path or "").strip()[:255] or None,
            source=(body.source or "").strip()[:80] or None,
            referrer=(body.referrer or "").strip()[:500] or None,
            metadata_json=metadata_json,
        )
    )
    db.commit()
    return {"recorded": True}


@router.get("/summary")
def get_usage_summary(
    days: int = Query(default=30),
    db: Session = Depends(get_db),
):
    if days not in ALLOWED_PERIODS:
        raise HTTPException(status_code=422, detail="days must be one of 7, 30 or 90")

    now = _now()
    end = datetime.combine(now.date() + timedelta(days=1), time.min)
    start = end - timedelta(days=days)
    previous_start = start - timedelta(days=days)

    visitors = _metric(
        db,
        column=UsageEvent.created_at,
        start=start,
        end=end,
        previous_start=previous_start,
        distinct_column=UsageEvent.user_id,
        filters=(UsageEvent.event_type == "home_view",),
    )
    page_views = _metric(
        db,
        column=UsageEvent.created_at,
        start=start,
        end=end,
        previous_start=previous_start,
        filters=(UsageEvent.event_type == "home_view",),
    )
    organizations = _metric(
        db,
        column=UsageEvent.created_at,
        start=start,
        end=end,
        previous_start=previous_start,
        distinct_column=UsageEvent.org_no,
        filters=(
            UsageEvent.event_type == "home_view",
            UsageEvent.org_no.is_not(None),
            UsageEvent.org_no != "",
        ),
    )
    conversations = _metric(
        db,
        column=ConversationMeta.created_at,
        start=start,
        end=end,
        previous_start=previous_start,
    )
    turns = _metric(
        db,
        column=ConversationTurn.started_at,
        start=start,
        end=end,
        previous_start=previous_start,
    )
    reports = _metric(
        db,
        column=ReportVersion.created_at,
        start=start,
        end=end,
        previous_start=previous_start,
        filters=(ReportVersion.source == "generate",),
    )
    llm_calls = _metric(
        db,
        column=LlmTokenUsageLog.start_time,
        start=start,
        end=end,
        previous_start=previous_start,
    )
    llm_total_tokens = _sum_metric(
        db,
        column=LlmTokenUsageLog.token_cost,
        timestamp_column=LlmTokenUsageLog.start_time,
        start=start,
        end=end,
        previous_start=previous_start,
    )
    llm_aggregate = (
        db.query(
            func.avg(LlmTokenUsageLog.token_cost),
            func.avg(LlmTokenUsageLog.time_spent),
            func.sum(case((LlmTokenUsageLog.exec_status == "SUCCESS", 1), else_=0)),
            func.sum(case((LlmTokenUsageLog.exec_status == "FAILED", 1), else_=0)),
        )
        .filter(
            LlmTokenUsageLog.start_time >= start,
            LlmTokenUsageLog.start_time < end,
        )
        .one()
    )
    llm_call_count = int(llm_calls["value"])
    llm_successful = int(llm_aggregate[2] or 0)
    llm_failed = int(llm_aggregate[3] or 0)
    llm_token_days = _daily_sums(
        db,
        LlmTokenUsageLog,
        LlmTokenUsageLog.start_time,
        LlmTokenUsageLog.token_cost,
        start,
        end,
    )
    llm_call_days = _daily_counts(
        db,
        LlmTokenUsageLog,
        LlmTokenUsageLog.start_time,
        start,
        end,
    )

    successful_turns = _count_in_period(
        db,
        ConversationTurn.started_at,
        start,
        end,
        filters=(ConversationTurn.status == "success",),
    )
    avg_duration_ms = (
        db.query(func.avg(ConversationTurn.duration_ms))
        .filter(
            ConversationTurn.started_at >= start,
            ConversationTurn.started_at < end,
            ConversationTurn.duration_ms.is_not(None),
        )
        .scalar()
    )
    total_turns = int(turns["value"])
    visitors_count = int(visitors["value"])
    conversation_users = _count_in_period(
        db,
        ConversationMeta.created_at,
        start,
        end,
        distinct_column=ConversationMeta.user_id,
    )
    report_users = int(
        db.query(func.count(distinct(AgentRunHistory.user_id)))
        .join(ReportVersion, ReportVersion.request_id == AgentRunHistory.request_id)
        .filter(
            ReportVersion.created_at >= start,
            ReportVersion.created_at < end,
            ReportVersion.source == "generate",
            AgentRunHistory.user_id.is_not(None),
        )
        .scalar()
        or 0
    )

    def visitor_rate(value: int) -> float:
        return round(value * 100 / visitors_count, 1) if visitors_count else 0.0

    visitor_days = _daily_counts(
        db,
        UsageEvent,
        UsageEvent.created_at,
        start,
        end,
        filters=(UsageEvent.event_type == "home_view",),
        distinct_column=UsageEvent.user_id,
    )
    conversation_days = _daily_counts(
        db,
        ConversationMeta,
        ConversationMeta.created_at,
        start,
        end,
    )
    report_days = _daily_counts(
        db,
        ReportVersion,
        ReportVersion.created_at,
        start,
        end,
        filters=(ReportVersion.source == "generate",),
    )
    trend = []
    llm_trend = []
    cursor: date = start.date()
    while cursor < end.date():
        key = cursor.isoformat()
        trend.append(
            {
                "date": key,
                "visitors": visitor_days.get(key, 0),
                "conversations": conversation_days.get(key, 0),
                "reports": report_days.get(key, 0),
            }
        )
        llm_trend.append(
            {
                "date": key,
                "tokens": llm_token_days.get(key, 0),
                "calls": llm_call_days.get(key, 0),
            }
        )
        cursor += timedelta(days=1)

    organization_rows = (
        db.query(
            UsageEvent.org_no,
            func.count(distinct(UsageEvent.user_id)),
            func.count(),
        )
        .filter(
            UsageEvent.event_type == "home_view",
            UsageEvent.created_at >= start,
            UsageEvent.created_at < end,
            UsageEvent.org_no.is_not(None),
            UsageEvent.org_no != "",
        )
        .group_by(UsageEvent.org_no)
        .order_by(func.count().desc())
        .limit(5)
        .all()
    )

    return {
        "period": {
            "days": days,
            "start": start.date().isoformat(),
            "end": now.date().isoformat(),
        },
        "metrics": {
            "visitors": visitors,
            "page_views": page_views,
            "organizations": organizations,
            "conversations": conversations,
            "turns": turns,
            "reports": reports,
            "success_rate": round(successful_turns * 100 / total_turns, 1) if total_turns else 0.0,
            "avg_duration_seconds": round(float(avg_duration_ms or 0) / 1000, 1),
        },
        "llm_usage": {
            "calls": llm_calls,
            "total_tokens": llm_total_tokens,
            "avg_tokens_per_call": round(float(llm_aggregate[0] or 0), 1),
            "avg_time_spent_ms": round(float(llm_aggregate[1] or 0), 1),
            "success_rate": (
                round(llm_successful * 100 / llm_call_count, 1)
                if llm_call_count
                else 0.0
            ),
            "successful_calls": llm_successful,
            "failed_calls": llm_failed,
            "trend": llm_trend,
        },
        "funnel": [
            {"key": "visitors", "label": "到访用户", "value": visitors_count, "rate": 100.0},
            {
                "key": "conversations",
                "label": "创建会话",
                "value": conversation_users,
                "rate": visitor_rate(conversation_users),
            },
            {
                "key": "reports",
                "label": "生成报告",
                "value": report_users,
                "rate": visitor_rate(report_users),
            },
        ],
        "trend": trend,
        "organizations": [
            {
                "org_no": org_no,
                "visitors": int(visitor_count or 0),
                "page_views": int(page_view_count or 0),
            }
            for org_no, visitor_count, page_view_count in organization_rows
        ],
    }


@router.get("/export")
def export_usage_details(
    days: int = Query(default=30),
    db: Session = Depends(get_db),
):
    if days not in ALLOWED_PERIODS:
        raise HTTPException(status_code=422, detail="days must be one of 7, 30 or 90")
    content = export_usage_details_xlsx(db, days)
    file_name = f"usage-details-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
    disposition = (
        f"attachment; filename=\"{file_name}\"; "
        f"filename*=UTF-8''{quote(file_name)}"
    )
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disposition},
    )
