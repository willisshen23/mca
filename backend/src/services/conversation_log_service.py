from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import asc, desc, or_

from src.infrastructure.db.models import ConversationTurn
from src.infrastructure.db.session import SessionLocal
from src.services.agent_run_history_service import (
    _now,
    _original_user_text,
    _serialize_datetime,
)

logger = logging.getLogger("activity-analysis.agent")

_RESPONSE_SUMMARY_LIMIT = 160


def record_turn_start(state: dict[str, Any]) -> None:
    """在一轮对话开始时落库（按 request_id upsert）"""
    request_id = str(state.get("request_id") or "").strip()
    if not request_id:
        logger.warning("conversation_turn start skipped: missing request_id")
        return

    try:
        user_text = _original_user_text(state)
        with SessionLocal() as db:
            row = (
                db.query(ConversationTurn)
                .filter(ConversationTurn.request_id == request_id)
                .first()
            )
            created = row is None
            if not row:
                row = ConversationTurn(request_id=request_id, started_at=_now())
                db.add(row)

            row.thread_id = str(state.get("thread_id") or "") or row.thread_id or ""
            row.user_id = str(state.get("user_id") or "") or None
            row.user_name = str(state.get("user_name") or "") or None
            row.org_no = str(state.get("org_no") or "") or None
            row.user_text = user_text
            row.channel = str(state.get("channel") or "") or None
            row.status = "running"
            row.assistant_response = None
            row.failure_reason = None
            row.has_report = False
            row.started_at = _now()
            row.finished_at = None
            row.duration_ms = None
            db.commit()
            logger.info(
                "conversation_turn start saved: request_id=%s thread_id=%s created=%s user_id=%s",
                request_id,
                row.thread_id,
                created,
                row.user_id or "-",
            )
    except Exception:
        logger.exception("conversation_turn start failed: request_id=%s", request_id)


def finish_turn(
    request_id: str,
    status: str,
    duration_ms: int,
    final_values: dict[str, Any] | None = None,
    failure_reason: str = "",
) -> None:
    """Update response, status, and duration after a conversation turn."""
    if not request_id:
        logger.warning("conversation_turn finish skipped: missing request_id status=%s", status)
        return

    final_values = final_values or {}
    try:
        with SessionLocal() as db:
            row = (
                db.query(ConversationTurn)
                .filter(ConversationTurn.request_id == request_id)
                .first()
            )
            if not row:
                logger.info(
                    "conversation_turn finish skipped: request_id=%s status=%s reason=row_not_found",
                    request_id,
                    status,
                )
                return
            row.status = status
            row.failure_reason = failure_reason or None
            row.assistant_response = str(final_values.get("final_response") or "") or None
            row.has_report = bool(str(final_values.get("html_report") or "").strip())
            row.finished_at = _now()
            row.duration_ms = duration_ms
            db.commit()
            logger.info(
                "conversation_turn finish saved: request_id=%s status=%s duration_ms=%d",
                request_id,
                status,
                duration_ms,
            )
    except Exception:
        logger.exception("conversation_turn finish failed: request_id=%s", request_id)


def list_turns(
    keyword: str = "",
    user_id: str = "",
    thread_id: str = "",
    status: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)
    with SessionLocal() as db:
        query = db.query(ConversationTurn)
        if user_id:
            query = query.filter(ConversationTurn.user_id.like(f"%{user_id}%"))
        if thread_id:
            query = query.filter(ConversationTurn.thread_id.like(f"%{thread_id}%"))
        if status:
            query = query.filter(ConversationTurn.status == status)
        if keyword:
            word = f"%{keyword}%"
            query = query.filter(
                or_(
                    ConversationTurn.request_id.like(word),
                    ConversationTurn.user_id.like(word),
                    ConversationTurn.user_name.like(word),
                    ConversationTurn.user_text.like(word),
                )
            )
        total = query.count()
        rows = (
            query.order_by(desc(ConversationTurn.started_at), desc(ConversationTurn.id))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "items": [_serialize_row(row, include_full=False) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


def get_thread_turns(thread_id: str) -> dict[str, Any]:
    """Return all turns for a thread ordered by time."""
    thread_id = (thread_id or "").strip()
    with SessionLocal() as db:
        rows = (
            db.query(ConversationTurn)
            .filter(ConversationTurn.thread_id == thread_id)
            .order_by(asc(ConversationTurn.started_at), asc(ConversationTurn.id))
            .all()
        )
        return {
            "thread_id": thread_id,
            "turns": [_serialize_row(row, include_full=True) for row in rows],
            "total": len(rows),
        }


def _serialize_row(row: ConversationTurn, include_full: bool) -> dict[str, Any]:
    response = row.assistant_response or ""
    payload = {
        "id": row.id,
        "request_id": row.request_id,
        "thread_id": row.thread_id,
        "user_id": row.user_id or "",
        "user_name": row.user_name or "",
        "user_text": row.user_text or "",
        "status": row.status,
        "failure_reason": row.failure_reason or "",
        "has_report": bool(row.has_report),
        "channel": row.channel or "",
        "started_at": _serialize_datetime(row.started_at),
        "finished_at": _serialize_datetime(row.finished_at),
        "duration_ms": row.duration_ms,
    }
    if include_full:
        payload["assistant_response"] = response
    else:
        summary = response[:_RESPONSE_SUMMARY_LIMIT]
        if len(response) > _RESPONSE_SUMMARY_LIMIT:
            summary += ""
        payload["response_summary"] = summary
    return payload
