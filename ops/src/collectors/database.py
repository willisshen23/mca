from __future__ import annotations

import asyncio
import time

from src.collectors.base import Sample


def _connect_mysql(settings):
    import pymysql

    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name or None,
        connect_timeout=int(settings.collector_timeout_s),
        read_timeout=int(settings.collector_timeout_s),
    )


def _probe_mysql(settings) -> Sample:
    start = time.monotonic()
    try:
        conn = _connect_mysql(settings)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            conn.close()
        return Sample("database", True, metrics={
            "mode": "mysql", "reachable": True,
            "latency_ms": int((time.monotonic() - start) * 1000), "error": None,
        })
    except Exception as exc:  # noqa: BLE001 - 不可达是正常探测结果
        return Sample("database", True, metrics={
            "mode": "mysql", "reachable": False, "latency_ms": None,
            "error": f"{type(exc).__name__}: {exc}",
        })


def _probe_sqlite(settings) -> Sample:
    data_dir = settings.main_app_dir / "data"
    files = []
    if data_dir.is_dir():
        for db in sorted(data_dir.glob("*.db")):
            try:
                size_mb = round(db.stat().st_size / 1024 / 1024, 1)
                with db.open("rb") as f:
                    f.read(1)
                files.append({"path": str(db), "size_mb": size_mb})
            except OSError:
                pass
    return Sample("database", True, metrics={
        "mode": "sqlite", "reachable": bool(files), "files": files,
    })


async def collect(settings) -> Sample:
    if settings.db_host:
        return await asyncio.to_thread(_probe_mysql, settings)
    return await asyncio.to_thread(_probe_sqlite, settings)
