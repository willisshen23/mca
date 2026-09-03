from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from src.services.conversation_log_service import get_thread_turns, list_turns

logger = logging.getLogger("activity-analysis.agent")

router = APIRouter(prefix="/conversation-logs")


@router.get("")
def api_list_conversation_logs(
    keyword: str = Query(default=""),
    user_id: str = Query(default=""),
    thread_id: str = Query(default=""),
    status: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return list_turns(
        keyword=keyword.strip(),
        user_id=user_id.strip(),
        thread_id=thread_id.strip(),
        status=status.strip(),
        limit=limit,
        offset=offset,
    )


@router.get("/thread/{thread_id}")
def api_get_thread_turns(thread_id: str):
    return get_thread_turns(thread_id)
