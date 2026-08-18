"""验收场景（对应规格第 8 节）：

1. 主应用进程被杀 + 日志有报错 → 巡检出红，诊断给出可用结论
2. LLM 网关不可用 → 巡检照常出红黄绿，诊断降级展示规则判定 + runbook
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.collectors.base import Sample
from src.diagnosis.pipeline import run_diagnosis
from src.inspection import run_inspection
from src.rules.engine import load_rules
from src.storage import OpsDB

_RULES = load_rules(Path(__file__).resolve().parents[1] / "src" / "rules" / "rules.yaml")


def _db(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    db.seed_runbooks(Path(__file__).resolve().parents[1] / "runbooks" / "seed")
    return db


def _down_collectors():
    """模拟主应用宕机：进程死、health 无响应、日志有报错、其余正常。"""
    async def process(s):
        return Sample("process", True, metrics={
            "pid": None, "alive": False,
            "health_ok": False, "health_status": None, "health_latency_ms": None,
        })

    async def logs(s):
        return Sample("logs", True, metrics={
            "error_count": 12, "warn_count": 0, "error_count_yesterday": 1,
            "clusters": {"memory": 12}, "files_scanned": 1,
        }, evidence=["ERROR MemoryError: unable to allocate"])

    def _ok(name, metrics):
        async def fn(s):
            return Sample(name, True, metrics=metrics)
        return fn

    return {
        "process": process,
        "logs": logs,
        "system": _ok("system", {"disk_pct": 40.0, "mem_pct": 95.0, "load1": 3.0}),
        "database": _ok("database", {"mode": "sqlite", "reachable": True, "files": []}),
        "llm_gateway": _ok("llm_gateway", {"configured": True, "reachable": True, "latency_s": 1.0, "error": None}),
        "bank_api": _ok("bank_api", {"endpoints": []}),
    }


def test_acceptance_main_app_down(settings):
    db = _db(settings)
    collectors = _down_collectors()

    payload = asyncio.run(run_inspection(settings, db, _RULES, collectors=collectors))
    assert payload["overall"] == "red"
    levels = {c["id"]: c["level"] for c in payload["checks"]}
    assert levels["process-alive"] == "red"
    assert levels["health-timeout"] == "red"
    assert levels["log-error-spike"] == "yellow"

    async def chat_ok(settings, messages):
        # 证据包必须包含进程状态与日志片段，供 LLM 定位
        assert '"alive": false' in messages[1]["content"]
        assert "MemoryError" in messages[1]["content"]
        return json.dumps({
            "causes": [{"cause": "内存不足被 OOM Kill", "confidence": "高",
                        "basis": "日志含 MemoryError 且内存 95%"}],
            "suggestions": [{"step": "重启主应用", "detail": "cd backend && bash scripts/server.sh start"}],
        }, ensure_ascii=False)

    result = asyncio.run(run_diagnosis(
        db, settings, "process-alive", chat_fn=chat_ok, collectors=collectors,
    ))
    assert result["degraded"] is False
    assert result["conclusion"]["causes"][0]["cause"] == "内存不足被 OOM Kill"


def test_acceptance_llm_down_degrades_to_runbook(settings):
    db = _db(settings)
    collectors = _down_collectors()

    async def chat_down(settings, messages):
        raise ConnectionError("网关不可达")

    result = asyncio.run(run_diagnosis(
        db, settings, "process-alive", chat_fn=chat_down, collectors=collectors,
    ))
    assert result["degraded"] is True
    assert result["rule_message"]                       # 规则判定原文
    assert "进程宕机" in result["runbook"]               # 出厂 process-down 手册全文
    assert "server.sh start" in result["runbook"]        # 手册里有可执行指引
