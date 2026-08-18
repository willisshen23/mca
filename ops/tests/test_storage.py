from __future__ import annotations

import json

from src.storage import OpsDB


def test_snapshot_roundtrip_and_latest(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    sid1 = db.save_snapshot("green", json.dumps({"overall": "green", "checks": []}))
    sid2 = db.save_snapshot("red", json.dumps({"overall": "red", "checks": [{"id": "x"}]}))
    assert sid2 > sid1

    latest = db.latest_snapshot()
    assert latest["overall"] == "red"
    assert latest["payload"]["checks"] == [{"id": "x"}]
    assert len(db.list_snapshots()) == 2


def test_purge_snapshots_keeps_recent(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    db.save_snapshot("green", "{}")
    db.purge_snapshots(days=7)
    assert len(db.list_snapshots()) == 1
    db.purge_snapshots(days=0)
    assert len(db.list_snapshots()) == 1  # days=0 按"刚写入的不删"处理：仅删早于 cutoff 的
    # 强制清理验证：直接删全部
    db._conn.execute("DELETE FROM snapshots")
    assert db.latest_snapshot() is None


def test_runbook_crud_and_category_lookup(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    db.upsert_runbook("llm-timeout", "LLM 超时", "llm-timeout", "正文v1")
    db.upsert_runbook("llm-timeout", "LLM 超时", "llm-timeout", "正文v2")

    rb = db.get_runbook("llm-timeout")
    assert rb["body"] == "正文v2"
    assert db.get_runbook_by_category("llm-timeout")["slug"] == "llm-timeout"
    assert db.get_runbook_by_category("nonexist") is None
    assert len(db.list_runbooks()) == 1


def test_seed_runbooks_only_imports_once(settings, tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "disk-full.md").write_text("# 磁盘满\n\n清理日志。\n")
    db = OpsDB(settings.ops_db_path)
    db.init()

    assert db.seed_runbooks(seed) == 1
    db.upsert_runbook("disk-full", "磁盘满(改)", "disk-full", "用户改过的正文")
    assert db.seed_runbooks(seed) == 0  # 不覆盖用户编辑
    assert db.get_runbook("disk-full")["body"] == "用户改过的正文"


def test_diagnosis_save_and_append(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    did = db.save_diagnosis("llm-latency", "LLM 延迟诊断", '{"causes":[]}',
                            '[{"role":"user","content":"q"}]', False, None)
    db.append_message(did, "assistant", "回答")

    diag = db.get_diagnosis(did)
    assert diag["check_id"] == "llm-latency"
    transcript = json.loads(diag["transcript"])
    assert transcript[-1] == {"role": "assistant", "content": "回答"}
    assert db.get_diagnosis(9999) is None
