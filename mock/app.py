"""Standalone FastAPI app for mock campaign data API.

Usage:
    cd mock && uvicorn app:app --reload --port 8001
"""
from __future__ import annotations

import logging
import os
import sys
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

try:
    from .router import router
    from .waihu_router import router as waihu_router
except ImportError:
    from router import router
    from waihu_router import router as waihu_router


def _resolve_log_level(level_name: str) -> int:
    level = getattr(logging, str(level_name or "INFO").upper(), None)
    return level if isinstance(level, int) else logging.INFO


log_level = _resolve_log_level(os.getenv("LOG_LEVEL", "INFO"))
_log = logging.getLogger("mock")
_log.setLevel(log_level)
if not _log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _log.addHandler(_handler)
_log.propagate = False

app = FastAPI(
    title="活动数据 Mock API",
    description="基于 Excel 样例数据的活动查询接口，支持按活动名称模糊搜索；同时提供活动模板清单查询接口以及外呼活动详情查询接口。",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(router, prefix="/api2")
app.include_router(waihu_router, prefix="/api")
app.include_router(waihu_router, prefix="/api2")


@app.middleware("http")
async def log_request(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        _log.info(
            "api_request method=%s path=%s status=%s cost_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    # 兼容两种启动方式：
    #   cd mock && python app.py          -> __package__ 为空
    #   cd ..  && python -m mock.app      -> __package__ = "mock"
    module_path = "mock.app:app" if __package__ else "app:app"
    uvicorn.run(
        module_path,
        host="0.0.0.0",
        port=8005,
        log_level=log_level,
        reload=True,
    )
