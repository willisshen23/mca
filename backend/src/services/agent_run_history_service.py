from __future__ import annotations

import io
import json
import logging
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import case, desc, func, inspect, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from src.config import get_settings, resolve_path
from src.infrastructure.db.models import (
    ActivityAnalysisTemplate,
    AgentRunHistory,
    ConversationMeta,
    ReportVersion,
)
from src.infrastructure.db.session import SessionLocal, engine
from src.domain.report.html_template import strip_report_footer_note
from src.services.report_export_service import prepare_report_html_for_download

logger = logging.getLogger("njbank.agent")

_MISSING: Any = object()


@dataclass(frozen=True)
class ReportAsset:
    content: bytes
    file_name: str
    media_type: str
    html: str


def ensure_agent_run_history_schema() -> None:
    inspector = inspect(engine)
    if "agent_run_history" not in inspector.get_table_names():
        return

    inspected_columns = inspector.get_columns("agent_run_history")
    existing_columns = {column["name"] for column in inspected_columns}
    column_types = {
        column["name"]: str(column.get("type") or "").upper()
        for column in inspected_columns
    }
    blob_type = "LONGBLOB" if engine.dialect.name == "mysql" else "BLOB"
    missing_columns = {
        "report_asset_name": "VARCHAR(255)",
        "report_asset_media_type": "VARCHAR(120)",
        "report_asset_blob": blob_type,
        "report_feedback": "VARCHAR(16)",
        "feedback_user_id": "VARCHAR(64)",
        "feedback_at": "DATETIME",
        "activity_template_snapshot": "JSON",
        "matched_data_template_name": "VARCHAR(255)",
        "org_no": "VARCHAR(64)",
        "activity_ids_json": "TEXT",
        "activity_names_json": "TEXT",
        "duration_ms": "INTEGER",
        "latest_version_no": "INTEGER",
    }
    with engine.begin() as conn:
        for column_name, column_type in missing_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE agent_run_history ADD COLUMN {column_name} {column_type}"))
            logger.info("agent_run_history schema upgraded: added column %s", column_name)
        for column_name in ("prompt_text", "final_response"):
            if (
                engine.dialect.name == "mysql"
                and column_name in existing_columns
                and "LONGTEXT" not in column_types.get(column_name, "")
            ):
                conn.execute(
                    text(
                        f"ALTER TABLE agent_run_history "
                        f"MODIFY COLUMN {column_name} LONGTEXT NULL"
                    )
                )
                logger.info(
                    "agent_run_history schema upgraded: %s %s -> LONGTEXT",
                    column_name,
                    column_types.get(column_name) or "unknown",
                )


def ensure_report_versions_schema() -> None:
    """Ensure report_versions 基建就绪并搬迁历史报告/反馈到版本表（幂等）。"""
    inspector = inspect(engine)
    table_names = {name.casefold() for name in inspector.get_table_names()}
    if "agent_run_history" not in table_names:
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("agent_run_history")
    }
    if "latest_version_no" not in existing_columns:
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE agent_run_history ADD COLUMN latest_version_no INTEGER")
            )
        logger.info("agent_run_history schema upgraded: added column latest_version_no")

    if "report_versions" not in table_names:
        # main.py 的 create 先行建表；表不存在时跳过数据搬迁
        return
    _migrate_report_versions_data()


def _migrate_report_versions_data() -> None:
    """把 agent_run_history 上的遗留报告资产/反馈搬为 v1 版本行（幂等）。"""
    with SessionLocal() as db:
        migrated_request_ids = {
            request_id
            for (request_id,) in db.query(ReportVersion.request_id).all()
        }
        rows = (
            db.query(AgentRunHistory)
            .filter(
                or_(
                    AgentRunHistory.report_asset_blob.isnot(None),
                    AgentRunHistory.report_file_path.isnot(None),
                )
            )
            .all()
        )
        migrated = 0
        for row in rows:
            if row.request_id in migrated_request_ids:
                continue
            blob = bytes(row.report_asset_blob) if row.report_asset_blob else None
            asset_name = row.report_asset_name
            media_type = row.report_asset_media_type
            if not blob:
                legacy_file = _get_legacy_report_path(row)
                if not legacy_file:
                    continue
                blob = build_report_asset_html(legacy_file.read_text(encoding="utf-8"))
                asset_name = asset_name or f"{legacy_file.stem}.html"
            db.add(
                ReportVersion(
                    request_id=row.request_id,
                    version_no=1,
                    report_asset_name=asset_name
                    or f"activity-analysis-report-{row.request_id}.html",
                    report_asset_media_type=media_type or "text/html; charset=utf-8",
                    report_asset_blob=blob,
                    source="generate",
                    feedback=row.report_feedback or None,
                    feedback_user_id=row.feedback_user_id,
                    feedback_at=row.feedback_at,
                )
            )
            row.latest_version_no = 1
            migrated += 1
        db.commit()
        if migrated:
            logger.info("report_versions migration: backfilled %d v1 rows", migrated)


def ensure_report_run_history(request_id: str, thread_id: str) -> None:
    clean_request_id = str(request_id or "").strip()
    if not clean_request_id:
        return

    with SessionLocal() as db:
        row = db.query(AgentRunHistory).filter(AgentRunHistory.request_id == clean_request_id).first()
        if row is None:
            row = AgentRunHistory(
                request_id=clean_request_id,
                thread_id=str(thread_id or ""),
                started_at=_now(),
            )
            db.add(row)
            db.commit()
            logger.info(
                "run_history ensured: request_id=%s thread_id=%s",
                clean_request_id,
                row.thread_id,
            )


def create_report_run_history(state: dict[str, Any]) -> None:
    request_id = str(state.get("request_id") or "").strip()
    selected_ids = state.get("selected_report_activity_ids") or []
    if not state.get("report_history_enabled") or not selected_ids:
        logger.info(
            "run_history create skipped: request_id=%s reason=not_selected_activity_report enabled=%s selected_count=%d",
            request_id or "-",
            bool(state.get("report_history_enabled")),
            len(selected_ids),
        )
        return

    if not request_id:
        logger.warning("run_history create skipped: missing request_id")
        return

    user_text = _original_user_text(state)
    with SessionLocal() as db:
        row = db.query(AgentRunHistory).filter(AgentRunHistory.request_id == request_id).first()
        created = row is None
        if not row:
            row = AgentRunHistory(
                request_id=request_id,
                thread_id=str(state.get("thread_id") or ""),
                started_at=_now(),
            )
            db.add(row)

        row.thread_id = str(state.get("thread_id") or "") or row.thread_id
        row.user_id = str(state.get("user_id") or "") or None
        row.user_name = str(state.get("user_name") or "") or None
        row.org_no = str(state.get("org_no") or "") or None
        activity_sources = [
            item
            for key in ("analysis_queue", "activity_list")
            for item in (state.get(key) or [])
            if isinstance(item, dict)
        ]
        activity_name_by_id = {
            str(
                item.get("activity_id")
                or item.get("act_no")
                or item.get("actNo")
                or item.get("活动编号")
                or ""
            ): str(
                item.get("name")
                or item.get("activity_name")
                or item.get("act_name")
                or item.get("actName")
                or item.get("活动名称")
                or ""
            )
            for item in activity_sources
        }
        clean_activity_ids = [str(item).strip() for item in selected_ids if str(item).strip()]
        row.activity_ids_json = json.dumps(clean_activity_ids, ensure_ascii=False)
        row.activity_names_json = json.dumps(
            [activity_name_by_id.get(activity_id, "") for activity_id in clean_activity_ids],
            ensure_ascii=False,
        )
        row.user_text = user_text
        row.status = "running"
        row.failure_reason = None
        row.final_response = None
        row.report_file_name = None
        row.report_file_path = None
        row.report_asset_name = None
        row.report_asset_media_type = None
        row.report_asset_blob = None
        row.report_feedback = None
        row.feedback_user_id = None
        row.feedback_at = None
        row.started_at = _now()
        row.finished_at = None
        row.duration_ms = None
        db.commit()
        logger.info(
            "run_history create saved: request_id=%s thread_id=%s created=%s user_id=%s selected_count=%d user_text=%s",
            request_id,
            row.thread_id,
            created,
            row.user_id or "-",
            len(selected_ids),
            (user_text or "")[:120],
        )


def _serialize_activity_template_snapshot(template: ActivityAnalysisTemplate | None) -> dict | None:
    if template is None:
        return None
    return {
        "code": template.code,
        "name": template.name,
        "type": template.type,
        "description": template.description,
        "skills_json": template.skills_json,
        "icon": template.icon,
        "color": template.color,
        "bg": template.bg,
        "status": template.status,
        "is_builtin": template.is_builtin,
    }


def record_template_match(
    request_id: str,
    activity_template: ActivityAnalysisTemplate,
    data_template_name: str | None,
) -> None:
    if not request_id:
        logger.warning("run_history template match skipped: missing request_id")
        return

    try:
        with SessionLocal() as db:
            row = db.query(AgentRunHistory).filter(AgentRunHistory.request_id == request_id).first()
            if not row:
                logger.info(
                    "run_history template match skipped: request_id=%s reason=row_not_found",
                    request_id,
                )
                return
            row.activity_template_snapshot = _serialize_activity_template_snapshot(activity_template)
            row.matched_data_template_name = data_template_name or None
            db.commit()
            logger.info(
                "run_history template match saved: request_id=%s template_code=%s template_name=%s data_template=%s",
                request_id,
                activity_template.code,
                activity_template.name,
                data_template_name or "-",
            )
    except Exception as exc:
        logger.warning(
            "run_history template match failed: request_id=%s error=%s",
            request_id,
            exc,
        )


def update_prompt_text(request_id: str, prompt_text: str) -> None:
    if not request_id:
        logger.warning("run_history prompt skipped: missing request_id")
        return
    with SessionLocal() as db:
        row = db.query(AgentRunHistory).filter(AgentRunHistory.request_id == request_id).first()
        if not row:
            logger.warning("run_history prompt skipped: request_id=%s reason=row_not_found", request_id)
            return
        row.prompt_text = prompt_text
        db.commit()
        logger.info("run_history prompt saved: request_id=%s chars=%d", request_id, len(prompt_text or ""))


def save_report_file(
    request_id: str,
    html_report: str,
    source: str = "generate",
    change_note: str | None = None,
) -> tuple[str, int | None]:
    """保存报告为新版本快照，返回 (asset_name, version_no)；失败返回 ("", None)。"""
    if not request_id or not html_report:
        logger.warning(
            "run_history report skipped: request_id=%s reason=%s",
            request_id or "-",
            "empty_report" if request_id else "missing_request_id",
        )
        return "", None

    asset_name = f"activity-analysis-report-{request_id}.html"
    asset_blob = build_report_asset_html(html_report)
    clean_source = source if source in {"generate", "modify"} else "generate"
    clean_note = str(change_note or "").strip()[:500] or None

    with SessionLocal() as db:
        row = db.query(AgentRunHistory).filter(AgentRunHistory.request_id == request_id).first()
        if not row:
            logger.warning("run_history report skipped: request_id=%s reason=row_not_found", request_id)
            return "", None
        version_no: int | None = None
        for attempt in range(2):
            max_version_no = (
                db.query(func.max(ReportVersion.version_no))
                .filter(ReportVersion.request_id == request_id)
                .scalar()
                or 0
            )
            version_no = max_version_no + 1
            db.add(
                ReportVersion(
                    request_id=request_id,
                    version_no=version_no,
                    report_asset_name=asset_name,
                    report_asset_media_type="text/html; charset=utf-8",
                    report_asset_blob=asset_blob,
                    source=clean_source,
                    change_note=clean_note if clean_source == "modify" else None,
                )
            )
            row.report_file_name = asset_name
            row.report_file_path = None
            row.latest_version_no = version_no
            try:
                db.commit()
                break
            except IntegrityError:
                db.rollback()
                version_no = None
                if attempt == 1:
                    logger.error(
                        "run_history report version conflict: request_id=%s retries exhausted",
                        request_id,
                    )
                    return "", None
                logger.warning(
                    "run_history report version conflict: request_id=%s retrying",
                    request_id,
                )

        logger.info(
            "run_history report version saved: request_id=%s version_no=%s source=%s html_chars=%d asset_bytes=%d",
            request_id,
            version_no,
            clean_source,
            len(html_report),
            len(asset_blob),
        )

    return asset_name, version_no


def finish_run_history(
    request_id: str,
    status: str,
    duration_ms: int,
    final_values: dict[str, Any] | None = None,
    failure_reason: str = "",
) -> None:
    if not request_id:
        logger.warning("run_history finish skipped: missing request_id status=%s", status)
        return

    final_values = final_values or {}
    with SessionLocal() as db:
        row = db.query(AgentRunHistory).filter(AgentRunHistory.request_id == request_id).first()
        if not row:
            logger.info(
                "run_history finish skipped: request_id=%s status=%s reason=row_not_found",
                request_id,
                status,
            )
            return
        row.status = status
        row.failure_reason = failure_reason or None
        row.final_response = str(final_values.get("final_response") or "") or None
        row.finished_at = _now()
        row.duration_ms = duration_ms
        db.commit()
        logger.info(
            "run_history finish saved: request_id=%s status=%s duration_ms=%d failure=%s",
            request_id,
            status,
            duration_ms,
            (failure_reason or "")[:120],
        )


FEEDBACK_COMMENT_MAX_LENGTH = 500


def _validate_feedback_input(feedback: str, comment: str | None) -> tuple[str, str]:
    clean_feedback = str(feedback or "").strip().lower()
    if clean_feedback not in {"like", "dislike", "none", ""}:
        raise ValueError("feedback must be like, dislike or none")
    clean_comment = str(comment or "").strip()
    if len(clean_comment) > FEEDBACK_COMMENT_MAX_LENGTH:
        raise ValueError(f"comment must be {FEEDBACK_COMMENT_MAX_LENGTH} characters or fewer")
    return clean_feedback, clean_comment


def _apply_version_feedback(
    version: ReportVersion,
    feedback: str,
    user_id: str,
    comment: str,
) -> None:
    if feedback in {"like", "dislike"}:
        version.feedback = feedback
        version.feedback_user_id = str(user_id or "").strip() or None
        version.feedback_at = _now()
        version.feedback_comment = comment if feedback == "dislike" else None
    else:
        version.feedback = None
        version.feedback_user_id = None
        version.feedback_at = None
        version.feedback_comment = None


def _get_latest_version(db, request_id: str) -> ReportVersion | None:
    return (
        db.query(ReportVersion)
        .options(defer(ReportVersion.report_asset_blob))
        .filter(ReportVersion.request_id == request_id)
        .order_by(desc(ReportVersion.version_no))
        .first()
    )


def update_report_feedback(
    request_id: str,
    feedback: str,
    user_id: str = "",
    version_no: int | None = None,
    comment: str | None = None,
) -> dict[str, Any] | None:
    clean_request_id = str(request_id or "").strip()
    clean_feedback, clean_comment = _validate_feedback_input(feedback, comment)
    if not clean_request_id:
        raise ValueError("request_id is required")

    with SessionLocal() as db:
        row = db.query(AgentRunHistory).filter(AgentRunHistory.request_id == clean_request_id).first()
        if not row:
            return None
        if version_no is not None:
            version = (
                db.query(ReportVersion)
                .filter(ReportVersion.request_id == clean_request_id)
                .filter(ReportVersion.version_no == version_no)
                .first()
            )
        else:
            version = _get_latest_version(db, clean_request_id)
        if version is None:
            return None
        _apply_version_feedback(version, clean_feedback, user_id, clean_comment)
        db.commit()
        logger.info(
            "run_history feedback saved: request_id=%s version_no=%s feedback=%s user_id=%s",
            clean_request_id,
            version.version_no,
            clean_feedback,
            version.feedback_user_id or "-",
        )
        payload = _serialize_row(row, include_prompt=False, db=db)
        # _serialize_row 返回的是最新版本的反馈信息，这里必须覆盖回
        # 实际被反馈的版本，否则调用方（前端卡片）会错误显示成最新版本号
        payload["version_no"] = version.version_no
        payload["report_feedback"] = version.feedback or ""
        payload["feedback_comment"] = version.feedback_comment or ""
        return payload


def update_latest_report_feedback_by_thread(
    thread_id: str,
    feedback: str,
    user_id: str = "",
    comment: str | None = None,
) -> dict[str, Any] | None:
    clean_thread_id = str(thread_id or "").strip()
    clean_feedback, clean_comment = _validate_feedback_input(feedback, comment)
    if not clean_thread_id:
        raise ValueError("thread_id is required")

    with SessionLocal() as db:
        row = (
            db.query(AgentRunHistory)
            .filter(AgentRunHistory.thread_id == clean_thread_id)
            .filter(AgentRunHistory.prompt_text.isnot(None))
            .filter(
                or_(
                    AgentRunHistory.latest_version_no.isnot(None),
                    AgentRunHistory.report_asset_name.isnot(None),
                    AgentRunHistory.report_file_path.isnot(None),
                )
            )
            .order_by(desc(AgentRunHistory.started_at), desc(AgentRunHistory.id))
            .first()
        )
        if not row:
            return None
        version = _get_latest_version(db, row.request_id)
        if version is None:
            return None
        _apply_version_feedback(version, clean_feedback, user_id, clean_comment)
        db.commit()
        logger.info(
            "run_history feedback saved by thread: thread_id=%s request_id=%s version_no=%s feedback=%s user_id=%s",
            clean_thread_id,
            row.request_id,
            version.version_no,
            clean_feedback,
            version.feedback_user_id or "-",
        )
        return _serialize_row(row, include_prompt=False, db=db)


def get_latest_report_html_by_thread(thread_id: str) -> str:
    """最新报告版本的 HTML 本体（P2 业务表驱动重载用），无报告时返回 ""。

    复用 get_report_asset 的版本回退链：latest_version_no 对应版本 →
    版本表最高版本 → 历史行 legacy blob → legacy 文件。
    """
    clean_thread_id = str(thread_id or "").strip()
    if not clean_thread_id:
        return ""

    with SessionLocal() as db:
        row = (
            db.query(AgentRunHistory.id)
            .filter(AgentRunHistory.thread_id == clean_thread_id)
            .filter(AgentRunHistory.prompt_text.isnot(None))
            .filter(
                or_(
                    AgentRunHistory.latest_version_no.isnot(None),
                    AgentRunHistory.report_asset_name.isnot(None),
                    AgentRunHistory.report_file_path.isnot(None),
                )
            )
            .order_by(desc(AgentRunHistory.started_at), desc(AgentRunHistory.id))
            .first()
        )
    if not row:
        return ""
    asset = get_report_asset(row.id)
    return asset.html if asset else ""


def get_latest_report_history_by_thread(thread_id: str) -> dict[str, Any] | None:
    clean_thread_id = str(thread_id or "").strip()
    if not clean_thread_id:
        return None

    with SessionLocal() as db:
        row = (
            db.query(AgentRunHistory)
            .options(defer(AgentRunHistory.report_asset_blob))
            .filter(AgentRunHistory.thread_id == clean_thread_id)
            .filter(AgentRunHistory.prompt_text.isnot(None))
            .filter(
                or_(
                    AgentRunHistory.latest_version_no.isnot(None),
                    AgentRunHistory.report_asset_name.isnot(None),
                    AgentRunHistory.report_file_path.isnot(None),
                )
            )
            .order_by(desc(AgentRunHistory.started_at), desc(AgentRunHistory.id))
            .first()
        )
        return _serialize_row(row, include_prompt=False, db=db) if row else None


def list_report_histories_by_thread(thread_id: str) -> list[dict[str, Any]]:
    """列出会话下全部报告运行历史（按生成时间升序），用于刷新后恢复所有报告卡片。"""
    clean_thread_id = str(thread_id or "").strip()
    if not clean_thread_id:
        return []

    with SessionLocal() as db:
        rows = (
            db.query(AgentRunHistory)
            .options(defer(AgentRunHistory.report_asset_blob))
            .filter(AgentRunHistory.thread_id == clean_thread_id)
            .filter(AgentRunHistory.prompt_text.isnot(None))
            .filter(
                or_(
                    AgentRunHistory.latest_version_no.isnot(None),
                    AgentRunHistory.report_asset_name.isnot(None),
                    AgentRunHistory.report_file_path.isnot(None),
                )
            )
            .order_by(AgentRunHistory.started_at, AgentRunHistory.id)
            .all()
        )
        # 同一 request_id 可能对应多行（如报告修改），只保留最新一行，避免重复恢复
        latest_by_request: dict[str, AgentRunHistory] = {}
        for row in rows:
            latest_by_request[row.request_id] = row
        result: list[dict[str, Any]] = []
        for row in latest_by_request.values():
            payload = _serialize_row(row, include_prompt=False, db=db)
            # 报告每次修改都会产生一个新版本，且前端直播时每轮追加一张报告卡片；
            # 返回全部版本号及每个版本各自的反馈，供刷新后逐版本恢复卡片。
            version_rows = (
                db.query(ReportVersion)
                .options(defer(ReportVersion.report_asset_blob))
                .filter(ReportVersion.request_id == row.request_id)
                .order_by(ReportVersion.version_no)
                .all()
            )
            payload["version_numbers"] = [version.version_no for version in version_rows]
            payload["versions"] = [
                {
                    "version_no": version.version_no,
                    "feedback": version.feedback or "",
                    "feedback_comment": version.feedback_comment or "",
                }
                for version in version_rows
            ]
            result.append(payload)
        return result


def _apply_feedback_filter(query, feedback: str):
    clean_feedback = str(feedback or "").strip().lower()
    if clean_feedback in {"like", "dislike"}:
        return query.filter(AgentRunHistory.report_feedback == clean_feedback)
    if clean_feedback == "none":
        return query.filter(
            or_(
                AgentRunHistory.report_feedback.is_(None),
                AgentRunHistory.report_feedback == "",
            )
        )
    return query


def _build_history_query(db, keyword: str, request_id: str, status: str, feedback: str):
    query = (
        db.query(AgentRunHistory)
        .options(defer(AgentRunHistory.report_asset_blob))
        .filter(AgentRunHistory.prompt_text.isnot(None))
    )
    if request_id:
        query = query.filter(AgentRunHistory.request_id.like(f"%{request_id}%"))
    if status:
        query = query.filter(AgentRunHistory.status == status)
    if keyword:
        word = f"%{keyword}%"
        query = query.filter(
            or_(
                AgentRunHistory.request_id.like(word),
                AgentRunHistory.user_id.like(word),
                AgentRunHistory.user_name.like(word),
                AgentRunHistory.user_text.like(word),
            )
        )
    return _apply_feedback_filter(query, feedback)


def list_run_histories(
    keyword: str = "",
    request_id: str = "",
    status: str = "",
    feedback: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    with SessionLocal() as db:
        query = _build_history_query(db, keyword, request_id, status, feedback)
        total = query.count()
        rows = (
            query.order_by(desc(AgentRunHistory.started_at), desc(AgentRunHistory.id))
            .offset(max(offset, 0))
            .limit(min(max(limit, 1), 500))
            .all()
        )
        return {
            "items": [_serialize_row(row, include_prompt=False, db=db) for row in rows],
            "total": total,
            "limit": min(max(limit, 1), 500),
            "offset": max(offset, 0),
        }


def get_run_history(history_id: int) -> dict[str, Any] | None:
    with SessionLocal() as db:
        row = (
            db.query(AgentRunHistory)
            .options(defer(AgentRunHistory.report_asset_blob))
            .filter(AgentRunHistory.id == history_id)
            .first()
        )
        return _serialize_row(row, include_prompt=True, db=db) if row else None


EXPORT_MAX_ROWS = 10000

_EXPORT_STATUS_TEXT = {
    "success": "成功",
    "failed": "失败",
    "cancelled": "已取消",
    "running": "运行中",
}

_EXPORT_FEEDBACK_TEXT = {
    "like": "已点赞",
    "dislike": "已点踩",
}


def export_run_histories_xlsx(
    keyword: str = "",
    request_id: str = "",
    status: str = "",
    feedback: str = "",
) -> bytes:
    from openpyxl import Workbook

    with SessionLocal() as db:
        rows = (
            _build_history_query(db, keyword, request_id, status, feedback)
            .order_by(desc(AgentRunHistory.started_at), desc(AgentRunHistory.id))
            .limit(EXPORT_MAX_ROWS)
            .all()
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "运行历史"
    sheet.append(
        [
            "时间",
            "request_id",
            "发起人",
            "会话名称",
            "分析模板",
            "数据模板",
            "状态",
            "耗时(ms)",
            "报告",
            "反馈",
            "反馈人",
            "失败原因",
        ]
    )
    for row in rows:
        snapshot = row.activity_template_snapshot or {}
        sheet.append(
            [
                _format_export_datetime(row.started_at),
                row.request_id or "",
                row.user_name or row.user_id or "",
                row.user_text or "",
                snapshot.get("name") or "",
                row.matched_data_template_name or "",
                _EXPORT_STATUS_TEXT.get(row.status, row.status or ""),
                row.duration_ms if row.duration_ms is not None else "",
                "已生成" if (row.report_asset_name or row.report_file_path) else "未生成",
                _EXPORT_FEEDBACK_TEXT.get(row.report_feedback or "", "未反馈"),
                row.feedback_user_id or "",
                row.failure_reason or "",
            ]
        )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _format_export_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


# ── 会话维度：管理后台"会话 → 报告"两级视图 ──

_SESSION_TITLE_FALLBACK_LIMIT = 50

_EXPORT_SOURCE_TEXT = {
    "generate": "生成",
    "modify": "修改",
}


def _has_report_clause():
    return or_(
        AgentRunHistory.latest_version_no.isnot(None),
        AgentRunHistory.report_asset_name.isnot(None),
        AgentRunHistory.report_file_path.isnot(None),
    )


def _parse_filter_date(value: str, *, end: bool = False) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        parsed = datetime.strptime(clean, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("date_from/date_to must use YYYY-MM-DD format") from exc
    return parsed + timedelta(days=1) if end else parsed


def _session_version_stats(db, thread_ids: list[str]) -> dict[str, dict[str, int]]:
    if not thread_ids:
        return {}
    like_case = case((ReportVersion.feedback == "like", 1), else_=0)
    dislike_case = case((ReportVersion.feedback == "dislike", 1), else_=0)
    rows = (
        db.query(
            AgentRunHistory.thread_id,
            func.count(ReportVersion.id),
            func.sum(like_case),
            func.sum(dislike_case),
        )
        .join(ReportVersion, ReportVersion.request_id == AgentRunHistory.request_id)
        .filter(AgentRunHistory.thread_id.in_(thread_ids))
        .group_by(AgentRunHistory.thread_id)
        .all()
    )
    return {
        thread_id: {
            "version_count": int(version_count or 0),
            "like_count": int(like_count or 0),
            "dislike_count": int(dislike_count or 0),
        }
        for thread_id, version_count, like_count, dislike_count in rows
    }


def _session_titles(db, thread_ids: list[str]) -> dict[str, str]:
    if not thread_ids:
        return {}
    titles = {
        meta.thread_id: (meta.title or "")
        for meta in db.query(ConversationMeta)
        .filter(ConversationMeta.thread_id.in_(thread_ids))
        .all()
    }
    for thread_id in thread_ids:
        if titles.get(thread_id):
            continue
        fallback = (
            db.query(AgentRunHistory.user_text)
            .filter(AgentRunHistory.thread_id == thread_id)
            .filter(AgentRunHistory.user_text.isnot(None))
            .filter(AgentRunHistory.user_text != "")
            .order_by(AgentRunHistory.started_at, AgentRunHistory.id)
            .first()
        )
        fallback_text = (fallback[0] if fallback else "") or ""
        titles[thread_id] = fallback_text[:_SESSION_TITLE_FALLBACK_LIMIT]
    return titles


def _keyword_session_filter(db, keyword: str):
    word = f"%{keyword}%"
    title_threads = db.query(ConversationMeta.thread_id).filter(
        ConversationMeta.title.like(word)
    )
    return or_(
        AgentRunHistory.user_id.like(word),
        AgentRunHistory.user_name.like(word),
        AgentRunHistory.request_id.like(word),
        AgentRunHistory.user_text.like(word),
        AgentRunHistory.thread_id.in_(title_threads),
    )


def list_report_sessions(
    keyword: str = "",
    feedback: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    parsed_from = _parse_filter_date(date_from)
    parsed_to = _parse_filter_date(date_to, end=True)
    clean_feedback = str(feedback or "").strip().lower()
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)

    with SessionLocal() as db:
        query = (
            db.query(
                AgentRunHistory.thread_id.label("thread_id"),
                func.max(AgentRunHistory.user_id).label("user_id"),
                func.max(AgentRunHistory.user_name).label("user_name"),
                func.count(AgentRunHistory.id).label("report_count"),
                func.max(AgentRunHistory.started_at).label("last_active_at"),
            )
            .filter(_has_report_clause())
            .group_by(AgentRunHistory.thread_id)
        )
        if keyword:
            query = query.filter(_keyword_session_filter(db, keyword))
        if clean_feedback in {"like", "dislike"}:
            feedback_threads = (
                db.query(AgentRunHistory.thread_id)
                .join(ReportVersion, ReportVersion.request_id == AgentRunHistory.request_id)
                .filter(ReportVersion.feedback == clean_feedback)
            )
            query = query.filter(AgentRunHistory.thread_id.in_(feedback_threads))
        elif clean_feedback == "none":
            feedback_threads = (
                db.query(AgentRunHistory.thread_id)
                .join(ReportVersion, ReportVersion.request_id == AgentRunHistory.request_id)
                .filter(ReportVersion.feedback.isnot(None))
            )
            query = query.filter(~AgentRunHistory.thread_id.in_(feedback_threads))
        if parsed_from is not None:
            query = query.having(func.max(AgentRunHistory.started_at) >= parsed_from)
        if parsed_to is not None:
            query = query.having(func.max(AgentRunHistory.started_at) < parsed_to)

        total = query.count()
        rows = (
            query.order_by(desc(func.max(AgentRunHistory.started_at)))
            .offset(offset)
            .limit(limit)
            .all()
        )
        thread_ids = [row.thread_id for row in rows]
        stats = _session_version_stats(db, thread_ids)
        titles = _session_titles(db, thread_ids)
        items = []
        for row in rows:
            row_stats = stats.get(row.thread_id) or {}
            items.append(
                {
                    "thread_id": row.thread_id,
                    "title": titles.get(row.thread_id) or "",
                    "user_id": row.user_id or "",
                    "user_name": row.user_name or "",
                    "report_count": int(row.report_count or 0),
                    "version_count": row_stats.get("version_count", 0),
                    "like_count": row_stats.get("like_count", 0),
                    "dislike_count": row_stats.get("dislike_count", 0),
                    "last_active_at": _serialize_datetime(row.last_active_at),
                }
            )
        return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_report_session_detail(thread_id: str) -> dict[str, Any] | None:
    clean_thread_id = str(thread_id or "").strip()
    if not clean_thread_id:
        return None

    with SessionLocal() as db:
        rows = (
            db.query(AgentRunHistory)
            .options(defer(AgentRunHistory.report_asset_blob))
            .filter(AgentRunHistory.thread_id == clean_thread_id)
            .filter(_has_report_clause())
            .order_by(desc(AgentRunHistory.started_at), desc(AgentRunHistory.id))
            .all()
        )
        if not rows:
            return None

        stats = _session_version_stats(db, [clean_thread_id]).get(clean_thread_id) or {}
        title = _session_titles(db, [clean_thread_id]).get(clean_thread_id) or ""
        versions = (
            db.query(ReportVersion)
            .options(defer(ReportVersion.report_asset_blob))
            .filter(ReportVersion.request_id.in_([row.request_id for row in rows]))
            .order_by(ReportVersion.request_id, ReportVersion.version_no)
            .all()
        )
        versions_by_request: dict[str, list[ReportVersion]] = {}
        for version in versions:
            versions_by_request.setdefault(version.request_id, []).append(version)

        first = rows[0]
        return {
            "thread_id": clean_thread_id,
            "title": title,
            "user_id": first.user_id or "",
            "user_name": first.user_name or "",
            "report_count": len(rows),
            "version_count": stats.get("version_count", 0),
            "like_count": stats.get("like_count", 0),
            "dislike_count": stats.get("dislike_count", 0),
            "last_active_at": _serialize_datetime(first.started_at),
            "reports": [
                _serialize_session_report(row, versions_by_request.get(row.request_id) or [])
                for row in rows
            ],
        }


def _serialize_session_report(
    row: AgentRunHistory, versions: list[ReportVersion]
) -> dict[str, Any]:
    return {
        "id": row.id,
        "request_id": row.request_id,
        "user_text": row.user_text or "",
        "status": row.status,
        "failure_reason": row.failure_reason or "",
        "started_at": _serialize_datetime(row.started_at),
        "finished_at": _serialize_datetime(row.finished_at),
        "duration_ms": row.duration_ms,
        "activity_template_snapshot": row.activity_template_snapshot or None,
        "matched_data_template_name": row.matched_data_template_name or None,
        "latest_version_no": row.latest_version_no,
        "versions": [_serialize_version_summary(version) for version in versions],
    }


def _serialize_version_summary(version: ReportVersion) -> dict[str, Any]:
    return {
        "version_id": version.id,
        "version_no": version.version_no,
        "source": version.source,
        "change_note": version.change_note or "",
        "created_at": _serialize_datetime(version.created_at),
        "feedback": version.feedback or "",
        "feedback_comment": version.feedback_comment or "",
        "feedback_user_id": version.feedback_user_id or "",
        "feedback_at": _serialize_datetime(version.feedback_at),
    }


def export_report_sessions_xlsx(
    keyword: str = "",
    feedback: str = "",
    date_from: str = "",
    date_to: str = "",
) -> bytes:
    from openpyxl import Workbook

    parsed_from = _parse_filter_date(date_from)
    parsed_to = _parse_filter_date(date_to, end=True)
    clean_feedback = str(feedback or "").strip().lower()

    with SessionLocal() as db:
        query = db.query(ReportVersion, AgentRunHistory).join(
            AgentRunHistory,
            AgentRunHistory.request_id == ReportVersion.request_id,
        )
        if keyword:
            query = query.filter(_keyword_session_filter(db, keyword))
        if clean_feedback in {"like", "dislike"}:
            query = query.filter(ReportVersion.feedback == clean_feedback)
        elif clean_feedback == "none":
            query = query.filter(ReportVersion.feedback.is_(None))
        if parsed_from is not None:
            query = query.filter(ReportVersion.created_at >= parsed_from)
        if parsed_to is not None:
            query = query.filter(ReportVersion.created_at < parsed_to)
        rows = (
            query.order_by(desc(ReportVersion.created_at), desc(ReportVersion.id))
            .limit(EXPORT_MAX_ROWS)
            .all()
        )
        titles = _session_titles(
            db,
            list({history.thread_id for _, history in rows}),
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "报告版本"
    sheet.append(
        [
            "时间",
            "会话标题",
            "发起人",
            "request_id",
            "版本号",
            "来源",
            "修改说明",
            "分析模板",
            "数据模板",
            "状态",
            "耗时(ms)",
            "反馈",
            "点踩原因",
            "反馈人",
            "反馈时间",
        ]
    )
    for version, history in rows:
        snapshot = history.activity_template_snapshot or {}
        sheet.append(
            [
                _format_export_datetime(version.created_at),
                titles.get(history.thread_id) or "",
                history.user_name or history.user_id or "",
                history.request_id or "",
                version.version_no,
                _EXPORT_SOURCE_TEXT.get(version.source, version.source or ""),
                version.change_note or "",
                snapshot.get("name") or "",
                history.matched_data_template_name or "",
                _EXPORT_STATUS_TEXT.get(history.status, history.status or ""),
                history.duration_ms if history.duration_ms is not None else "",
                _EXPORT_FEEDBACK_TEXT.get(version.feedback or "", "未反馈"),
                version.feedback_comment or "",
                version.feedback_user_id or "",
                _format_export_datetime(version.feedback_at),
            ]
        )

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def get_report_asset(history_id: int, version_no: int | None = None) -> ReportAsset | None:
    with SessionLocal() as db:
        row = db.query(AgentRunHistory).filter(AgentRunHistory.id == history_id).first()
        if not row:
            return None

        version_query = db.query(ReportVersion).filter(
            ReportVersion.request_id == row.request_id
        )
        if version_no is not None:
            version = version_query.filter(ReportVersion.version_no == version_no).first()
            if version is None:
                return None
        else:
            version = version_query.order_by(desc(ReportVersion.version_no)).first()

        if version is not None and version.report_asset_blob:
            content = bytes(version.report_asset_blob)
            return ReportAsset(
                content=content,
                file_name=version.report_asset_name
                or f"activity-analysis-report-{row.request_id}.html",
                media_type=version.report_asset_media_type or "text/html; charset=utf-8",
                html=extract_report_html_from_asset(content),
            )
        if version_no is not None:
            return None

        if row.report_asset_blob:
            content = bytes(row.report_asset_blob)
            file_name = row.report_asset_name or row.report_file_name or f"activity-analysis-report-{row.request_id}.html"
            return ReportAsset(
                content=content,
                file_name=file_name,
                media_type=row.report_asset_media_type or "text/html; charset=utf-8",
                html=extract_report_html_from_asset(content),
            )

        legacy_file = _get_legacy_report_path(row)
        if not legacy_file:
            return None
        html = strip_report_footer_note(legacy_file.read_text(encoding="utf-8"))
        return ReportAsset(
            content=build_report_asset_html(html),
            file_name=f"{legacy_file.stem}.html",
            media_type="text/html; charset=utf-8",
            html=html,
        )


def get_report_file(history_id: int) -> tuple[Path, str] | None:
    with SessionLocal() as db:
        row = db.query(AgentRunHistory).filter(AgentRunHistory.id == history_id).first()
        if not row:
            return None
        file_path = _get_legacy_report_path(row)
        if not file_path:
            return None
        return file_path, row.report_file_name or file_path.name


def build_report_asset_html(html_report: str) -> bytes:
    return _prepare_report_html_for_asset(html_report).encode("utf-8")


def build_report_asset_zip(html_report: str) -> bytes:
    html = _prepare_report_html_for_asset(html_report)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", html.encode("utf-8"))
        _write_static_asset(archive, "echarts.min.js")
        if _needs_tabler_assets(html):
            _write_static_asset(archive, "tabler-icons.min.css")
            for font_name in ("tabler-icons.woff2", "tabler-icons.woff", "tabler-icons.ttf"):
                _write_static_asset(archive, f"fonts/{font_name}")
    return buffer.getvalue()


def extract_report_html_from_asset(content: bytes) -> str:
    if not content:
        return ""
    try:
        with zipfile.ZipFile(io.BytesIO(content), mode="r") as archive:
            try:
                return strip_report_footer_note(archive.read("index.html").decode("utf-8"))
            except KeyError:
                first_html = next((name for name in archive.namelist() if name.lower().endswith(".html")), "")
                if not first_html:
                    return ""
                return strip_report_footer_note(archive.read(first_html).decode("utf-8"))
    except zipfile.BadZipFile:
        return strip_report_footer_note(content.decode("utf-8", errors="ignore"))


def _serialize_row(row: AgentRunHistory, include_prompt: bool, db=None) -> dict[str, Any]:
    latest_version = _get_latest_version(db, row.request_id) if db is not None else None
    if latest_version is not None:
        feedback = latest_version.feedback or ""
        feedback_comment = latest_version.feedback_comment or ""
        feedback_user_id = latest_version.feedback_user_id or ""
        feedback_at = _serialize_datetime(latest_version.feedback_at)
        version_no: int | None = latest_version.version_no
    else:
        feedback = row.report_feedback or ""
        feedback_comment = ""
        feedback_user_id = row.feedback_user_id or ""
        feedback_at = _serialize_datetime(row.feedback_at)
        version_no = None
    latest_version_no = row.latest_version_no
    if latest_version_no is None and latest_version is not None:
        latest_version_no = latest_version.version_no
    payload = {
        "id": row.id,
        "request_id": row.request_id,
        "thread_id": row.thread_id,
        "user_id": row.user_id or "",
        "user_name": row.user_name or "",
        "user_text": row.user_text or "",
        "status": row.status,
        "failure_reason": row.failure_reason or "",
        "final_response": row.final_response or "",
        "report_file_name": (
            latest_version.report_asset_name
            if latest_version is not None
            else (row.report_asset_name or row.report_file_name or "")
        ),
        "has_report": bool(
            latest_version is not None or row.report_asset_name or row.report_file_path
        ),
        "latest_version_no": latest_version_no,
        "version_no": version_no,
        "report_feedback": feedback,
        "feedback_comment": feedback_comment,
        "feedback_user_id": feedback_user_id,
        "feedback_at": feedback_at,
        "started_at": _serialize_datetime(row.started_at),
        "finished_at": _serialize_datetime(row.finished_at),
        "activity_template_snapshot": row.activity_template_snapshot or None,
        "matched_data_template_name": row.matched_data_template_name or None,
        "duration_ms": row.duration_ms,
    }
    if include_prompt:
        payload["prompt_text"] = row.prompt_text or ""
    return payload


def _get_legacy_report_path(row: AgentRunHistory) -> Path | None:
    if not row.report_file_path:
        return None
    file_path = Path(row.report_file_path).resolve()
    settings = get_settings()
    report_root = (resolve_path(settings.output_dir) / "reports").resolve()
    if file_path != report_root and not str(file_path).startswith(str(report_root) + os.sep):
        return None
    if not file_path.exists():
        return None
    return file_path


def _prepare_report_html_for_asset(html_report: str) -> str:
    html = prepare_report_html_for_download(html_report)
    html = re.sub(r'(["\'])/lib/tabler-icons\.min\.css\1', r"\1./tabler-icons.min.css\1", html)
    html = html.replace("/lib/tabler-icons.min.css", "./tabler-icons.min.css")

    if _needs_tabler_assets(html) and "tabler-icons.min.css" not in html:
        link = '<link rel="stylesheet" href="./tabler-icons.min.css">'
        if re.search(r"</head\s*>", html, flags=re.IGNORECASE):
            html = re.sub(r"</head\s*>", f"{link}</head>", html, count=1, flags=re.IGNORECASE)
        else:
            html = f"{link}\n{html}"
    return html


def _needs_tabler_assets(html: str) -> bool:
    lowered = (html or "").lower()
    return "tabler-icons" in lowered or 'class="ti ' in lowered or "class='ti " in lowered or " ti-" in lowered


def _write_static_asset(archive: zipfile.ZipFile, relative_path: str) -> None:
    static_path = _static_lib_dir() / relative_path
    if not static_path.exists():
        logger.warning("report asset dependency missing: %s", static_path)
        return
    archive.write(static_path, relative_path)


def _static_lib_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "infrastructure" / "static" / "lib"


def _original_user_text(state: dict[str, Any]) -> str:
    explicit = str(state.get("original_user_text") or "").strip()
    if explicit and not _is_selection_continue_text(explicit):
        return explicit

    messages = state.get("messages") or []
    for message in messages:
        content = _message_content(message).strip()
        # 消息对象已绝迹（v3 全是 dict）；非 dict 一律按属性兜底取 type
        message_type = getattr(message, "type", "") if not isinstance(message, dict) else ""
        if isinstance(message, dict):
            message_type = str(message.get("type") or message.get("role") or "")
        if message_type in {"human", "user"} and content and not _is_selection_continue_text(content):
            return content
    for message in messages:
        content = _message_content(message).strip()
        if content and not _is_selection_continue_text(content):
            return content
    return ""


def _is_selection_continue_text(text_value: str) -> bool:
    normalized = text_value.strip()
    return normalized.startswith("\u5df2\u9009\u62e9") and "\u7ee7\u7eed\u5206\u6790" in normalized


def _message_content(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content") or "")
    # 历史遗留消息对象按属性兜底取 content；无 content 属性（如纯字符串）直接 str
    content = getattr(message, "content", _MISSING)
    if content is not _MISSING:
        return str(content or "")
    return str(message)


def _serialize_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)
