from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse, FileResponse

from src.config import get_settings

logger = logging.getLogger("njbank.agent")
router = APIRouter(prefix="/logs")

settings = get_settings()


def _get_log_dir() -> Path:
    log_dir = Path(settings.log_dir)
    if not log_dir.is_absolute():
        log_dir = Path(__file__).resolve().parent.parent.parent.parent / log_dir
    return log_dir


@router.get("/files")
def list_log_files():
    """列出所有日志文件"""
    log_dir = _get_log_dir()
    if not log_dir.exists():
        return {"files": [], "total": 0}

    files = []
    base_name = Path(settings.log_file).stem or "app"
    ext = Path(settings.log_file).suffix or ".log"
    
    for f in sorted(log_dir.glob(f"{base_name}-*{ext}"), reverse=True):
        files.append({
            "name": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "modified_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    
    return {"files": files, "total": len(files)}


@router.get("/content")
def get_log_content(
    filename: str = Query(..., description="日志文件名"),
    lines: int = Query(100, ge=1, le=5000, description="读取行数"),
    tail: bool = Query(True, description="是否从尾部读取"),
):
    """读取日志文件内容"""
    log_dir = _get_log_dir()
    filepath = log_dir / filename
    
    if not filepath.exists():
        return PlainTextResponse(content=f"文件不存在: {filename}", status_code=404)
    
    if not str(filepath).startswith(str(log_dir)):
        return PlainTextResponse(content="非法路径", status_code=400)
    
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            if tail:
                content = "".join(all_lines[-lines:])
            else:
                content = "".join(all_lines[:lines])
        return PlainTextResponse(content=content)
    except Exception as e:
        logger.error("读取日志文件失败: %s", str(e))
        return PlainTextResponse(content=f"读取失败: {str(e)}", status_code=500)


@router.get("/download/{filename}")
def download_log_file(filename: str):
    """下载日志文件"""
    log_dir = _get_log_dir()
    filepath = log_dir / filename
    
    if not filepath.exists():
        return PlainTextResponse(content=f"文件不存在: {filename}", status_code=404)
    
    if not str(filepath).startswith(str(log_dir)):
        return PlainTextResponse(content="非法路径", status_code=400)
    
    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="text/plain",
    )


@router.get("/tail")
def tail_log(
    lines: int = Query(100, ge=1, le=1000),
    filename: str = Query(None, description="指定日志文件名，不指定则取最新的"),
):
    """获取最新日志内容"""
    log_dir = _get_log_dir()
    
    if not log_dir.exists():
        return PlainTextResponse(content="日志目录不存在", status_code=404)
    
    if not filename:
        base_name = Path(settings.log_file).stem or "app"
        ext = Path(settings.log_file).suffix or ".log"
        files = sorted(log_dir.glob(f"{base_name}-*{ext}"), reverse=True)
        if not files:
            return PlainTextResponse(content="暂无日志文件", status_code=404)
        filepath = files[0]
    else:
        filepath = log_dir / filename
    
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            content = "".join(all_lines[-lines:])
        return PlainTextResponse(content=content)
    except Exception as e:
        logger.error("读取日志文件失败: %s", str(e))
        return PlainTextResponse(content=f"读取失败: {str(e)}", status_code=500)