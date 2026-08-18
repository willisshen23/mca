from __future__ import annotations

import os
import time

import httpx

from src.collectors.base import Sample


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _probe_health(url: str, timeout: float):
    """返回 (health_ok, status_code|None, latency_ms|None)。"""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
        latency_ms = int((time.monotonic() - start) * 1000)
        return resp.status_code == 200, resp.status_code, latency_ms
    except Exception:  # noqa: BLE001 - 探测失败即"不健康"
        return False, None, None


async def collect(settings) -> Sample:
    pid = None
    try:
        raw = settings.main_pid_file.read_text().strip()
        pid = int(raw) if raw.isdigit() else None
    except OSError:
        pid = None

    alive = _pid_alive(pid) if pid else False
    health_ok, status, latency = await _probe_health(
        settings.main_health_url, settings.collector_timeout_s
    )
    return Sample(
        "process",
        True,
        metrics={
            "pid": pid,
            "alive": alive,
            "health_ok": health_ok,
            "health_status": status,
            "health_latency_ms": latency,
        },
    )
