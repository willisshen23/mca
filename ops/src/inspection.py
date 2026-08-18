from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from src.collectors import COLLECTORS
from src.collectors.base import run_collector
from src.rules.engine import evaluate

logger = logging.getLogger("ops.inspection")

_LEVEL_ORDER = {"green": 0, "gray": 1, "yellow": 2, "red": 3}


async def run_inspection(settings, db, rules, collectors=None) -> dict:
    """执行一轮巡检：并行采集 → 规则判定 → 快照入库 → 返回 payload。"""
    collectors = collectors or COLLECTORS
    samples_list = await asyncio.gather(*(
        run_collector(name, fn, settings) for name, fn in collectors.items()
    ))
    samples = {s.collector: s for s in samples_list}
    checks = evaluate(samples, rules)
    overall = "green"
    for check in checks:
        if _LEVEL_ORDER[check.level] > _LEVEL_ORDER[overall]:
            overall = check.level

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "checks": [asdict(c) for c in checks],
        "samples": {name: asdict(s) for name, s in samples.items()},
    }
    try:
        snapshot_id = db.save_snapshot(overall, json.dumps(payload, ensure_ascii=False))
        db.purge_snapshots(settings.snapshot_retention_days)
        payload["id"] = snapshot_id
        payload["persisted"] = True
    except Exception:  # noqa: BLE001 - ops 库损坏/磁盘满时降级为仅返回结果
        logger.exception("巡检快照入库失败，本轮结果仅实时展示")
        payload["id"] = None
        payload["persisted"] = False
    return payload


async def scheduler_loop(settings, db, rules, stop_event) -> None:
    """后台定时巡检：启动即跑一轮，之后每 interval 分钟一轮；单轮失败不中断循环。"""
    while not stop_event.is_set():
        try:
            await run_inspection(settings, db, rules)
        except Exception:  # noqa: BLE001 - 巡检失败不杀死调度器
            logger.exception("定时巡检执行失败")
        interval = max(settings.inspect_interval_minutes, 0) * 60
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval or 0.001)
        except asyncio.TimeoutError:
            pass
