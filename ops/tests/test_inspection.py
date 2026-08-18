from __future__ import annotations

import asyncio

from src.collectors.base import Sample
from src.inspection import run_inspection, scheduler_loop
from src.rules.engine import Rule
from src.storage import OpsDB


def _rules():
    return [
        Rule("process-alive", "进程", "process", "process_alive"),
        Rule("disk-usage", "磁盘", "system", "disk_usage", {"warn_pct": 85, "red_pct": 95}),
    ]


def _db(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    return db


def _collectors(process_alive=True, disk_pct=50.0):
    async def process_collect(s):
        return Sample("process", True, metrics={"alive": process_alive})

    async def system_collect(s):
        return Sample("system", True, metrics={"disk_pct": disk_pct})

    return {"process": process_collect, "system": system_collect}


def test_run_inspection_overall_red_and_persisted(settings):
    db = _db(settings)
    payload = asyncio.run(
        run_inspection(settings, db, _rules(), collectors=_collectors(process_alive=False))
    )
    assert payload["overall"] == "red"
    levels = {c["id"]: c["level"] for c in payload["checks"]}
    assert levels == {"process-alive": "red", "disk-usage": "green"}

    latest = db.latest_snapshot()
    assert latest["id"] == payload["id"]
    assert latest["payload"]["overall"] == "red"


def test_run_inspection_gray_beats_green(settings):
    db = _db(settings)

    async def broken(s):
        raise RuntimeError("x")

    collectors = _collectors()
    collectors["system"] = broken
    payload = asyncio.run(run_inspection(settings, db, _rules(), collectors=collectors))
    assert payload["overall"] == "gray"


def test_run_inspection_degrades_when_db_broken(settings):
    """ops SQLite 损坏时：巡检照常返回结果，仅标记 persisted=False（规格 6 降级）。"""
    db = _db(settings)
    db._conn.execute("DROP TABLE snapshots")  # 模拟库损坏

    payload = asyncio.run(
        run_inspection(settings, db, _rules(), collectors=_collectors())
    )
    assert payload["overall"] == "green"
    assert payload["persisted"] is False
    assert payload["id"] is None


def test_scheduler_loop_runs_then_stops(settings):
    db = _db(settings)
    settings.inspect_interval_minutes = 0  # 立即进入下一轮
    stop = asyncio.Event()
    runs = []

    original = run_inspection

    async def counting(settings, db, rules, collectors=None):
        runs.append(1)
        if len(runs) >= 2:
            stop.set()
        return await original(settings, db, rules, collectors=_collectors())

    import src.inspection as insp

    async def _main():
        insp_run = counting
        # scheduler_loop 内部调用模块级 run_inspection，这里直接替换引用
        insp.run_inspection = insp_run
        try:
            await asyncio.wait_for(scheduler_loop(settings, db, _rules(), stop), timeout=5)
        finally:
            insp.run_inspection = original

    asyncio.run(_main())
    assert len(runs) >= 2
