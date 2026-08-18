from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.api.schemas import UploadResponse
from src.config import get_settings, resolve_path
from src.services.uploaded_file_service import summarize_uploaded_file

logger = logging.getLogger("njbank.agent")

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".xls", ".xlsx", ".xlsm", ".xltx", ".xltm"}
REPORT_EXPORT_MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
}


def _safe_child_file(root: Path, file_name: str) -> Path:
    if (
        not file_name
        or file_name != Path(file_name).name
        or ".." in file_name
        or "/" in file_name
        or "\\" in file_name
    ):
        raise HTTPException(status_code=400, detail="无效的文件名")

    resolved_root = root.resolve()
    file_path = (resolved_root / file_name).resolve()
    if file_path.parent != resolved_root:
        raise HTTPException(status_code=403, detail="禁止访问")
    return file_path


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    settings = get_settings()
    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"涓嶆敮鎸佺殑鏂囦欢绫诲瀷: {extension}锛屼粎鏀寔 {ALLOWED_EXTENSIONS}")

    upload_dir = resolve_path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex[:8]
    safe_name = f"{file_id}_{file.filename}"
    file_path = upload_dir / safe_name

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds limit: {settings.max_upload_size_mb} MB",
        )

    file_path.write_bytes(content)

    try:
        summary_str = summarize_uploaded_file(str(file_path))
        summary = json.loads(summary_str)
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"鏂囦欢瑙ｆ瀽澶辫触: {str(exc)}") from exc

    preview = {
        "rows": summary.get("rows", 0),
        "columns": summary.get("columns", 0),
        "column_names": summary.get("column_names", []),
        "sample_data": summary.get("sample_data", []),
    }

    logger.info("鏂囦欢涓婁紶鎴愬姛: %s (%d琛?x %d鍒?", file.filename, preview["rows"], preview["columns"])

    return UploadResponse(
        file_id=file_id,
        file_name=file.filename,
        file_path=str(file_path.resolve()),
        preview=preview,
        message=f"Upload succeeded: {preview['rows']} rows, {preview['columns']} columns",
    )


@router.get("/download/{file_name}")
async def download_file(file_name: str):
    if ".." in file_name or "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail="鏃犳晥鐨勬枃浠跺悕")

    settings = get_settings()
    output_dir = resolve_path(settings.output_dir)
    file_path = (output_dir / file_name).resolve()

    resolved_root = output_dir.resolve()
    if not str(file_path).startswith(str(resolved_root) + os.sep) and file_path != resolved_root:
        raise HTTPException(status_code=403, detail="绂佹璁块棶")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(
        path=str(file_path),
        filename=file_name,
        media_type=media_type,
    )


@router.get("/report-exports/{file_name}")
async def download_report_export(file_name: str):
    extension = Path(file_name).suffix.lower()
    media_type = REPORT_EXPORT_MEDIA_TYPES.get(extension)
    if not media_type:
        raise HTTPException(status_code=400, detail="不支持的报告文件类型")

    settings = get_settings()
    if settings.report_export_dir:
        export_dir = resolve_path(settings.report_export_dir)
    else:
        import tempfile

        export_dir = Path(tempfile.gettempdir()) / "njbank_exports"

    file_path = _safe_child_file(export_dir, file_name)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="报告文件不存在或已失效")

    return FileResponse(
        path=str(file_path),
        filename=file_name,
        media_type=media_type,
    )
