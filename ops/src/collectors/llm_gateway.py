from __future__ import annotations

import time

import httpx

from src.collectors.base import Sample


async def _probe(settings, transport=None) -> Sample:
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    headers = {}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=settings.collector_timeout_s, transport=transport
        ) as client:
            resp = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
        latency = round(time.monotonic() - start, 2)
        reachable = resp.status_code == 200
        return Sample("llm_gateway", True, metrics={
            "configured": True, "reachable": reachable, "latency_s": latency,
            "error": None if reachable else f"HTTP {resp.status_code}",
        })
    except Exception as exc:  # noqa: BLE001 - 探测失败即结果
        return Sample("llm_gateway", True, metrics={
            "configured": True, "reachable": False, "latency_s": None,
            "error": f"{type(exc).__name__}: {exc}",
        })


async def collect(settings) -> Sample:
    if not settings.llm_base_url:
        return Sample("llm_gateway", True, metrics={
            "configured": False, "reachable": False, "latency_s": None,
            "error": "未配置 LLM 网关",
        })
    return await _probe(settings)
