from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.infrastructure.db.models import ConversationMeta, ConversationTurn, ReportVersion
from src.infrastructure.db.session import get_db
from src.services.agent_run_history_service import (
    get_latest_report_history_by_thread,
    get_latest_report_html_by_thread,
    list_report_histories_by_thread,
)
from src.services.conversation_log_service import get_thread_turns
from src.domain.report.html_template import strip_report_footer_note

router = APIRouter(prefix="/conversations")


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _naive_dt(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min
    return value.replace(tzinfo=None) if value.tzinfo else value


def _report_placements(db: Session, thread_id: str, report_histories: list[dict]) -> list[dict]:
    """推算每份报告每个版本在消息流中的原始位置。

    直播时每产生一个版本就追加一张报告卡片，位置在产生它的用户轮次之后、
    下一轮用户消息之前。这里按版本创建时间锚定到对应的用户轮次序号
    （user_turn 为第几条用户消息，0 起），前端据此把恢复的报告卡片插回原位。
    """
    if not report_histories:
        return []
    turns = (
        db.query(ConversationTurn)
        .filter(ConversationTurn.thread_id == thread_id)
        .order_by(ConversationTurn.id)
        .all()
    )
    # 审批恢复轮次（"已审批 …"）不产生新的用户消息，锚定时排除
    usable_turns = [t for t in turns if not str(t.user_text or "").startswith("已审批")]
    versions = (
        db.query(ReportVersion)
        .filter(ReportVersion.request_id.in_([h["request_id"] for h in report_histories]))
        .order_by(ReportVersion.created_at, ReportVersion.id)
        .all()
    )
    placements = []
    for version in versions:
        # 最后一个 started_at <= 版本创建时间的用户轮次即为锚点
        user_turn = len(usable_turns) - 1
        for index, turn in enumerate(usable_turns):
            if _naive_dt(turn.started_at) > _naive_dt(version.created_at):
                user_turn = index - 1
                break
        placements.append({
            "request_id": version.request_id,
            "version_no": version.version_no,
            "user_turn": user_turn if usable_turns else -1,
        })
    return placements


def _messages_from_turns(turns: list[dict]) -> list[dict]:
    """conversation_turn 全量轮次 → 聊天消息列表（v2/v3 通吃）。

    过滤口径（与 _report_placements 既有口径一致）：
    - 审批恢复轮（user_text 以"已审批"开头的审计文本）不产生用户消息；
    - status=failed 且无回复的轮次整体丢弃；
    - 其余轮次：user_text → user 消息，有 assistant_response 再补 ai 消息。
    """
    messages = []
    for turn in turns:
        user_text = str(turn.get("user_text") or "")
        if user_text.startswith("已审批"):
            continue
        assistant_response = str(turn.get("assistant_response") or "")
        if turn.get("status") == "failed" and not assistant_response.strip():
            continue
        if user_text.strip():
            messages.append({"role": "user", "content": user_text})
        if assistant_response.strip():
            messages.append({"role": "ai", "content": assistant_response})
    return messages


class CreateConversationRequest(BaseModel):
    user_id: str
    title: str = "新建分析对话"


class UpdateConversationRequest(BaseModel):
    user_id: str
    title: str


def get_current_user_id(
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> str:
    """Read user id from query param or X-User-Id header."""
    uid = x_user_id or user_id
    if not uid:
        raise HTTPException(status_code=400, detail="Missing user_id: provide via query param or X-User-Id header")
    return uid


@router.get("")
def list_conversations(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """List conversations for current user."""
    rows = (
        db.query(ConversationMeta)
        .filter(ConversationMeta.user_id == user_id)
        .order_by(desc(ConversationMeta.updated_at))
        .all()
    )

    conversations = []
    for row in rows:
        conversations.append({
            "id": row.thread_id,
            "title": row.title or "未命名对话",
            "agent_version": row.agent_version,
            "updated_at": _serialize_datetime(row.updated_at),
            "created_at": _serialize_datetime(row.created_at),
        })

    return {"conversations": conversations}


@router.post("")
def create_conversation(
    body: CreateConversationRequest,
    db: Session = Depends(get_db),
):
    """Create a new conversation."""
    thread_id = str(uuid.uuid4())
    agent_version = "v2"

    meta = ConversationMeta(
        thread_id=thread_id,
        user_id=body.user_id,
        title=body.title or "新建分析对话",
        agent_version=agent_version,
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)

    return {
        "id": meta.thread_id,
        "title": meta.title,
        "agent_version": meta.agent_version,
        "created_at": _serialize_datetime(meta.created_at),
    }


@router.get("/{thread_id}")
async def get_conversation(
    thread_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """获取单个对话详情（含消息历史）"""
    meta = (
        db.query(ConversationMeta)
        .filter(ConversationMeta.thread_id == thread_id)
        .first()
    )
    if not meta:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if meta.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问该对话")

    # P2 起重载只读业务表（v2/v3 通吃），不再读任何 checkpoint：
    # - messages：conversation_turn 全量轮次重建（user_text/assistant_response）
    # - html_report：report_versions 最新版本 HTML 本体
    # - report_context / runtime_trace：checkpoint 专属瞬态，降级为空（字段保留）
    messages = _messages_from_turns(get_thread_turns(thread_id)["turns"])
    html_report = strip_report_footer_note(get_latest_report_html_by_thread(thread_id))

    report_histories = list_report_histories_by_thread(thread_id)
    return {
        "id": meta.thread_id,
        "title": meta.title or "未命名对话",
        "agent_version": meta.agent_version,
        "messages": messages,
        "html_report": html_report,
        "report_context": {},
        "report_history": get_latest_report_history_by_thread(thread_id) if html_report else None,
        "report_histories": report_histories,
        "report_placements": _report_placements(db, thread_id, report_histories),
        "runtime_trace": {},
        "updated_at": _serialize_datetime(meta.updated_at),
        "created_at": _serialize_datetime(meta.created_at),
    }


@router.patch("/{thread_id}")
def update_conversation(
    thread_id: str,
    body: UpdateConversationRequest,
    db: Session = Depends(get_db),
):
    """Rename a conversation."""
    meta = (
        db.query(ConversationMeta)
        .filter(ConversationMeta.thread_id == thread_id)
        .first()
    )
    if not meta:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if meta.user_id != body.user_id:
        raise HTTPException(status_code=403, detail="无权访问该对话")

    meta.title = body.title
    db.commit()
    db.refresh(meta)

    return {
        "id": meta.thread_id,
        "title": meta.title,
        "updated_at": _serialize_datetime(meta.updated_at),
    }


@router.delete("/{thread_id}")
async def delete_conversation(
    thread_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Delete a conversation and checkpoint data."""
    meta = (
        db.query(ConversationMeta)
        .filter(ConversationMeta.thread_id == thread_id)
        .first()
    )
    if not meta:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if meta.user_id != user_id:
        raise HTTPException(status_code=403, detail="无权访问该对话")

    # 删除 v3 (openjiuwen persistence) checkpoint 数据；文件/表不存在时静默跳过
    from src.agent_v3.state.persistence import delete_v3_thread_checkpoint

    await delete_v3_thread_checkpoint(thread_id)

    # 删除元数据
    db.delete(meta)
    db.commit()

    return {"status": "deleted"}
