from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import src.main as main_module
from src.main import create_app
from src.storage import OpsDB


@pytest.fixture
def client(settings, monkeypatch):
    settings.ops_token = "secret-token"
    db = OpsDB(settings.ops_db_path)
    db.init()

    async def fake_inspection(settings, db, rules, collectors=None):
        payload = {"created_at": "2026-08-06T00:00:00+00:00", "overall": "green",
                   "checks": [], "samples": {}}
        payload["id"] = db.save_snapshot("green", json.dumps(payload))
        return payload

    async def fake_diagnosis(db, settings, check_id, **kwargs):
        did = db.save_diagnosis(check_id, "测试剧本", '{"causes":[]}', "[]", False, None)
        return {"id": did, "check_id": check_id, "degraded": False,
                "conclusion": {"causes": []}}

    monkeypatch.setattr(main_module, "run_inspection", fake_inspection)
    monkeypatch.setattr(main_module, "run_diagnosis", fake_diagnosis)
    app = create_app(settings=settings, db=db)
    return TestClient(app)  # 不用 with 语法，避免触发 lifespan 定时循环


AUTH = {"X-Ops-Token": "secret-token"}


def test_health_is_open(client):
    assert client.get("/api/health").status_code == 200


def test_token_required(client):
    assert client.get("/api/inspections/latest").status_code == 401
    assert client.get("/api/inspections/latest", headers={"X-Ops-Token": "wrong"}).status_code == 401


def test_latest_snapshot_empty_then_present(client):
    resp = client.get("/api/inspections/latest", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["overall"] == "gray"

    run = client.post("/api/inspections/run", headers=AUTH)
    assert run.status_code == 200 and run.json()["overall"] == "green"

    latest = client.get("/api/inspections/latest", headers=AUTH).json()
    assert latest["overall"] == "green"
    history = client.get("/api/inspections/history", headers=AUTH).json()
    assert len(history) == 1


def test_diagnosis_create_and_get(client):
    resp = client.post("/api/diagnoses", json={"check_id": "llm-latency"}, headers=AUTH)
    assert resp.status_code == 200
    did = resp.json()["id"]

    detail = client.get(f"/api/diagnoses/{did}", headers=AUTH).json()
    assert detail["check_id"] == "llm-latency"
    assert detail["conclusion"] == {"causes": []}

    assert client.get("/api/diagnoses/9999", headers=AUTH).status_code == 404


def test_runbook_crud(client):
    resp = client.post("/api/runbooks", headers=AUTH, json={
        "slug": "disk-full", "title": "磁盘满", "category": "disk-full", "body": "清理日志",
    })
    assert resp.status_code == 200

    assert client.get("/api/runbooks", headers=AUTH).json()[0]["slug"] == "disk-full"

    resp = client.put("/api/runbooks/disk-full", headers=AUTH, json={
        "title": "磁盘满(更新)", "category": "disk-full", "body": "新正文",
    })
    assert resp.status_code == 200
    assert client.get("/api/runbooks/disk-full", headers=AUTH).json()["body"] == "新正文"
