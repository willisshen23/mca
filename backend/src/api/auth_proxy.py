"""AuthSDK 鉴权服务反向代理。

镜像部署时浏览器直连本服务（无前置 nginx），前端 AuthSDK 的
/login、/register/send_code、/register、/check_login 请求经
/activity/authApi/* 打到本服务，由这里剥掉 /activity/authApi 前缀转发到鉴权服务
（AUTH_SERVICE_BASE_URL，如 http://1.95.124.163:5003）。
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from src.config import get_settings

logger = logging.getLogger("activity-analysis.agent")

router = APIRouter()

_client: httpx.AsyncClient | None = None

# 请求/响应中都不转发的 hop-by-hop 头；host/content-length 由 httpx 按上游重写
_HOP_BY_HOP_HEADERS = frozenset({
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
})


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(follow_redirects=True)
    return _client


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_auth_api(path: str, request: Request) -> Response:
    settings = get_settings()
    base_url = settings.auth_service_base_url.strip().rstrip("/")
    if not base_url:
        return JSONResponse(
            status_code=503,
            content={"detail": "鉴权服务未配置（AUTH_SERVICE_BASE_URL 为空）"},
        )

    query = request.url.query
    upstream_url = f"{base_url}/{path}" + (f"?{query}" if query else "")
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _HOP_BY_HOP_HEADERS
    }

    try:
        upstream = await _get_client().request(
            request.method,
            upstream_url,
            content=await request.body(),
            headers=headers,
            timeout=settings.auth_service_timeout_seconds,
        )
    except httpx.TimeoutException:
        logger.warning("authApi 代理超时: %s %s", request.method, upstream_url)
        return JSONResponse(status_code=504, content={"detail": "鉴权服务响应超时"})
    except httpx.HTTPError as exc:
        logger.warning("authApi 代理失败: %s %s -> %s", request.method, upstream_url, exc)
        return JSONResponse(status_code=502, content={"detail": "鉴权服务不可达"})

    # httpx 已解压响应体，需去掉 content-encoding/content-length，避免与 body 不符
    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in _HOP_BY_HOP_HEADERS and k.lower() != "content-encoding"
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )
