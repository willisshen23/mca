from __future__ import annotations

import asyncio
import shutil
from collections import namedtuple

from src.collectors import database, system

_Usage = namedtuple("usage", "total used free")


def test_system_disk_pct_takes_max(settings, monkeypatch):
    def fake_usage(path):
        if "logs" in str(path):
            return _Usage(100, 90, 10)   # 90%
        return _Usage(100, 50, 50)       # 50%

    monkeypatch.setattr(shutil, "disk_usage", fake_usage)
    monkeypatch.setattr(system, "_read_mem_pct", lambda: 42.0)

    sample = asyncio.run(system.collect(settings))

    assert sample.metrics["disk_pct"] == 90.0
    assert sample.metrics["mem_pct"] == 42.0


def test_database_sqlite_mode(settings):
    db_file = settings.main_app_dir / "data" / "skills.db"
    db_file.write_bytes(b"x" * 1024)

    sample = asyncio.run(database.collect(settings))

    assert sample.metrics["mode"] == "sqlite"
    assert sample.metrics["reachable"] is True
    assert sample.metrics["files"][0]["path"].endswith("skills.db")


def test_database_sqlite_missing_dir(settings):
    settings.main_app_dir = settings.main_app_dir / "gone"

    sample = asyncio.run(database.collect(settings))

    assert sample.metrics["mode"] == "sqlite"
    assert sample.metrics["reachable"] is False


def test_database_mysql_reachable(settings, monkeypatch):
    settings.db_host = "10.0.0.1"

    class _Cursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql): assert sql == "SELECT 1"

    class _Conn:
        def cursor(self): return _Cursor()
        def close(self): pass

    monkeypatch.setattr(database, "_connect_mysql", lambda s: _Conn())

    sample = asyncio.run(database.collect(settings))

    assert sample.metrics["mode"] == "mysql"
    assert sample.metrics["reachable"] is True
    assert sample.metrics["latency_ms"] is not None


def test_database_mysql_refused(settings, monkeypatch):
    settings.db_host = "10.0.0.1"

    def refuse(s):
        raise ConnectionError("refused")

    monkeypatch.setattr(database, "_connect_mysql", refuse)

    sample = asyncio.run(database.collect(settings))

    assert sample.metrics["reachable"] is False
    assert "refused" in sample.metrics["error"]
