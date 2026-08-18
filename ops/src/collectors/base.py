from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class Sample:
    collector: str
    ok: bool
    metrics: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


async def run_collector(name, fn, settings, timeout_s=None) -> Sample:
    """执行单个采集器：永不抛异常，失败/超时返回 ok=False 的 Sample。"""
    start = time.monotonic()
    try:
        sample = await asyncio.wait_for(
            fn(settings), timeout_s or settings.collector_timeout_s
        )
        sample.collector = name
        sample.duration_ms = int((time.monotonic() - start) * 1000)
        return sample
    except Exception as exc:  # noqa: BLE001 - 兜底是设计意图
        return Sample(
            collector=name,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
