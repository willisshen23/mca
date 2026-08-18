from __future__ import annotations

import asyncio
import time

import httpx

from src.collectors.base import Sample


async def _probe_one(url: str, token: str, timeout: float, transport=None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            resp = await client.post(url, json={}, headers=headers)
        return {
            "url": url, "reachable": True, "status": resp.status_code,
            "latency_ms": int((time.monotonic() - start) * 1000),
        }
    except Exception:  # noqa: BLE001 - 探测失败即结果
        return {"url": url, "reachable": False, "status": None, "latency_ms": None}


async def _probe_all(settings, transport=None) -> Sample:
    endpoints = await asyncio.gather(*(
        _probe_one(url, settings.bank_api_token, settings.collector_timeout_s, transport)
        for url in settings.bank_api_urls
    ))
    return Sample("bank_api", True, metrics={"endpoints": list(endpoints)})


async def collect(settings) -> Sample:
    return await _probe_all(settings)
