from __future__ import annotations

import asyncio
import os
import shutil

from src.collectors.base import Sample


def _read_mem_pct() -> float | None:
    """读 /proc/meminfo；非 Linux（如开发机 macOS）返回 None。"""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = int(rest.strip().split()[0])
        total, available = info["MemTotal"], info["MemAvailable"]
        return round((1 - available / total) * 100, 1)
    except (OSError, KeyError, ZeroDivisionError):
        return None


def _scan_sync(settings) -> Sample:
    pcts = []
    worst_path = ""
    for path in {settings.main_app_dir.resolve(), settings.log_dir.resolve()}:
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        pct = round(usage.used / usage.total * 100, 1)
        pcts.append(pct)
        if pct == max(pcts):
            worst_path = str(path)
    try:
        load1 = round(os.getloadavg()[0], 2)
    except OSError:
        load1 = None
    return Sample("system", True, metrics={
        "disk_pct": max(pcts) if pcts else None,
        "disk_path": worst_path,
        "mem_pct": _read_mem_pct(),
        "load1": load1,
    })


async def collect(settings) -> Sample:
    return await asyncio.to_thread(_scan_sync, settings)
