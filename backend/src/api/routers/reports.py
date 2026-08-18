from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.services.report_export_service import prepare_report_html_for_download

router = APIRouter(prefix="/reports")


class ReportHtmlRequest(BaseModel):
    html: str = Field(default="")
    title: str = Field(default="Activity Analysis Report")


@router.post("/html")
def api_create_report_html(body: ReportHtmlRequest):
    html = (body.html or "").strip()
    if not html:
        raise HTTPException(
            status_code=400,
            detail="Report content is empty, HTML cannot be generated",
        )

    content = prepare_report_html_for_download(html)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/html",
        headers={
            "Content-Disposition": 'attachment; filename="activity-analysis-report.html"'
        },
    )
