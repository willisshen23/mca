from __future__ import annotations

import io
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.api.schemas import ReportFeedbackUpdate
from src.services.agent_run_history_service import (
    export_report_sessions_xlsx,
    export_run_histories_xlsx,
    get_report_asset,
    get_report_session_detail,
    get_run_history,
    list_report_sessions,
    list_run_histories,
    update_latest_report_feedback_by_thread,
    update_report_feedback,
)

router = APIRouter(prefix="/agent-run-history")


@router.get("")
def api_list_run_histories(
    keyword: str = Query(default=""),
    request_id: str = Query(default=""),
    status: str = Query(default=""),
    feedback: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    return list_run_histories(
        keyword=keyword.strip(),
        request_id=request_id.strip(),
        status=status.strip(),
        feedback=feedback.strip(),
        limit=limit,
        offset=offset,
    )


@router.get("/export")
def api_export_run_histories(
    keyword: str = Query(default=""),
    request_id: str = Query(default=""),
    status: str = Query(default=""),
    feedback: str = Query(default=""),
):
    content = export_run_histories_xlsx(
        keyword=keyword.strip(),
        request_id=request_id.strip(),
        status=status.strip(),
        feedback=feedback.strip(),
    )
    file_name = f"agent-run-history-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(file_name)},
    )


@router.get("/sessions")
def api_list_report_sessions(
    keyword: str = Query(default=""),
    feedback: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        return list_report_sessions(
            keyword=keyword.strip(),
            feedback=feedback.strip(),
            date_from=date_from.strip(),
            date_to=date_to.strip(),
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions/export")
def api_export_report_sessions(
    keyword: str = Query(default=""),
    feedback: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    try:
        content = export_report_sessions_xlsx(
            keyword=keyword.strip(),
            feedback=feedback.strip(),
            date_from=date_from.strip(),
            date_to=date_to.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    file_name = f"report-versions-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(file_name)},
    )


@router.get("/sessions/{thread_id}")
def api_get_report_session_detail(thread_id: str):
    detail = get_report_session_detail(thread_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Resource not found")
    return detail


@router.get("/{history_id}")
def api_get_run_history(history_id: int):
    row = get_run_history(history_id)
    if not row:
        raise HTTPException(status_code=404, detail="Resource not found")
    return row


@router.post("/{request_id}/feedback")
def api_update_report_feedback(request_id: str, body: ReportFeedbackUpdate):
    try:
        row = update_report_feedback(
            request_id,
            body.feedback,
            body.user_id,
            version_no=body.version_no,
            comment=body.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="Report history not found")
    return row


@router.post("/thread/{thread_id}/feedback")
def api_update_latest_report_feedback_by_thread(thread_id: str, body: ReportFeedbackUpdate):
    try:
        row = update_latest_report_feedback_by_thread(
            thread_id,
            body.feedback,
            body.user_id,
            comment=body.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail="Report history not found")
    return row


@router.get("/{history_id}/report")
def api_download_report(
    history_id: int,
    format: str = Query(default="html"),
    version_no: int | None = Query(default=None),
):
    asset = get_report_asset(history_id, version_no=version_no)
    if not asset:
        raise HTTPException(status_code=404, detail="Resource not found")

    target_format = (format or "html").strip().lower()
    if target_format != "html":
        raise HTTPException(
            status_code=400,
            detail="Unsupported report format, only html is supported",
        )

    return StreamingResponse(
        io.BytesIO(asset.content),
        media_type=asset.media_type or "text/html; charset=utf-8",
        headers={"Content-Disposition": _content_disposition(asset.file_name)},
    )


def _content_disposition(file_name: str) -> str:
    safe_name = file_name or "activity-analysis-report.html"
    return f"attachment; filename*=UTF-8''{quote(safe_name)}"
