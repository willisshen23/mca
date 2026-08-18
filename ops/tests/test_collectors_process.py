from __future__ import annotations

import asyncio

import pytest

from src.collectors import process
from src.collectors.base import Sample, run_collector


def test_run_collector_returns_sample(settings):
    async def ok_fn(s):
        return Sample("demo", True, metrics={"x": 1})

    sample = asyncio.run(run_collector("demo", ok_fn, settings))
    assert sample.ok and sample.metrics == {"x": 1} and sample.duration_ms >= 0


def test_run_collector_catches_exception(settings):
    async def boom(s):
        raise RuntimeError("炸了")

    sample = asyncio.run(run_collector("demo", boom, settings))
    assert sample.ok is False
    assert "炸了" in sample.error


def test_run_collector_timeout(settings):
    settings.collector_timeout_s = 0.05

    async def slow(s):
        await asyncio.sleep(5)

    sample = asyncio.run(run_collector("demo", slow, settings))
    assert sample.ok is False
    assert "TimeoutError" in sample.error


def _patch_health(monkeypatch, ok=True, status=200, latency=12):
    async def fake_probe(url, timeout):
        return ok, status, latency

    monkeypatch.setattr(process, "_probe_health", fake_probe)


def test_process_alive_and_health_ok(settings, monkeypatch):
    settings.main_pid_file.write_text("12345")
    monkeypatch.setattr(process, "_pid_alive", lambda pid: True)
    _patch_health(monkeypatch)

    sample = asyncio.run(process.collect(settings))

    assert sample.ok
    assert sample.metrics == {
        "pid": 12345, "alive": True,
        "health_ok": True, "health_status": 200, "health_latency_ms": 12,
    }


def test_process_missing_pid_file(settings, monkeypatch):
    _patch_health(monkeypatch, ok=False, status=None, latency=None)

    sample = asyncio.run(process.collect(settings))

    assert sample.metrics["pid"] is None
    assert sample.metrics["alive"] is False
    assert sample.metrics["health_ok"] is False
