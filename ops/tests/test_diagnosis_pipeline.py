from __future__ import annotations

import asyncio
import json

import pytest

from src.collectors.base import Sample
from src.diagnosis.pipeline import (
    DEFAULT_PLAYBOOK,
    PLAYBOOKS,
    followup,
    parse_conclusion,
    run_diagnosis,
)
from src.storage import OpsDB


def _db(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    return db


def _collectors():
    async def fake(settings):
        return Sample("fake", True, metrics={"ok": 1})

    return {name: fake for name in
            ("process", "logs", "system", "database", "llm_gateway", "bank_api")}


async def _chat_ok(settings, messages):
    return json.dumps({
        "causes": [{"cause": "网关负载高", "confidence": "高", "basis": "延迟45s"}],
        "suggestions": [{"step": "联系网关管理员", "detail": "确认负载"}],
    }, ensure_ascii=False)


def test_parse_conclusion_tolerant():
    assert parse_conclusion('{"causes": [], "suggestions": []}') == {"causes": [], "suggestions": []}
    fenced = '前言```json\n{"causes": [{"cause": "x"}]}\n```后记'
    assert parse_conclusion(fenced)["causes"] == [{"cause": "x"}]
    assert parse_conclusion("不是JSON") == {"raw": "不是JSON"}


def test_playbooks_cover_builtin_rules():
    for check_id in ("process-alive", "health-timeout", "log-error-spike",
                     "disk-usage", "mysql-unreachable", "llm-latency", "bank-api"):
        assert check_id in PLAYBOOKS
    assert DEFAULT_PLAYBOOK.check_id == "*"


def test_run_diagnosis_success(settings):
    db = _db(settings)
    db.upsert_runbook("llm-timeout", "LLM 超时手册", "llm-timeout", "手册正文")

    result = asyncio.run(run_diagnosis(
        db, settings, "llm-latency", chat_fn=_chat_ok, collectors=_collectors(),
    ))

    assert result["degraded"] is False
    assert result["conclusion"]["causes"][0]["cause"] == "网关负载高"
    diag = db.get_diagnosis(result["id"])
    assert diag["playbook"] == "LLM 网关延迟诊断"
    transcript = json.loads(diag["transcript"])
    assert "手册正文" in transcript[1]["content"]   # runbook 已注入提示词


def test_run_diagnosis_degraded_when_llm_down(settings):
    db = _db(settings)
    db.upsert_runbook("llm-timeout", "LLM 超时手册", "llm-timeout", "手册正文")
    db.save_snapshot("red", json.dumps({
        "overall": "red",
        "checks": [{"id": "llm-latency", "title": "LLM 网关延迟",
                    "level": "red", "message": "LLM 网关响应严重超时（45s）"}],
        "samples": {},
    }))

    async def chat_down(settings, messages):
        raise ConnectionError("网关挂了")

    result = asyncio.run(run_diagnosis(
        db, settings, "llm-latency", chat_fn=chat_down, collectors=_collectors(),
    ))

    assert result["degraded"] is True
    assert result["rule_message"] == "LLM 网关响应严重超时（45s）"
    assert result["runbook"] == "手册正文"
    assert "网关挂了" in result["error"]


def test_followup_appends_and_returns(settings):
    db = _db(settings)
    first = asyncio.run(run_diagnosis(
        db, settings, "disk-usage", chat_fn=_chat_ok, collectors=_collectors(),
    ))

    async def chat_reply(settings, messages):
        assert messages[-1] == {"role": "user", "content": "怎么确认？"}
        return "看 disk_pct 指标"

    answer = asyncio.run(followup(db, settings, first["id"], "怎么确认？", chat_fn=chat_reply))
    assert answer["answer"] == "看 disk_pct 指标"

    transcript = json.loads(db.get_diagnosis(first["id"])["transcript"])
    assert transcript[-2:] == [
        {"role": "user", "content": "怎么确认？"},
        {"role": "assistant", "content": "看 disk_pct 指标"},
    ]

    with pytest.raises(KeyError):
        asyncio.run(followup(db, settings, 9999, "x", chat_fn=chat_reply))
