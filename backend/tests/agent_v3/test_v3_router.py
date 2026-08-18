"""路由测试：/v2/agent/* 无条件委托 v3 runtime（v3 已是唯一运行时）。

router 定义在 src/api/routers/agent_v2.py，prefix="/v2/agent"，
测试 app 直接 include_router（不挂 /api 前缀），故测试 URL 为 /v2/agent/*。
"""

from httpx import ASGITransport, AsyncClient

from src.agent_v3 import runtime as v3_runtime


async def _fake_stream(**kwargs):
    yield 'data: {"type": "done", "payload": {}}\n\n'


def _make_app(router_mod):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router_mod.router)
    return app


async def test_run_delegates_to_v3(monkeypatch):
    from src.api.routers import agent_v2 as router_mod

    calls = []

    async def spy(**kwargs):
        calls.append(kwargs)
        return _fake_stream(**kwargs)

    monkeypatch.setattr(v3_runtime, "start_buffered_agent_run", spy)
    app = _make_app(router_mod)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/v2/agent/run", json={"thread_id": "t1", "message": "hi"})
    assert resp.status_code == 200
    assert calls and calls[0]["thread_id"] == "t1"


async def test_resume_delegates_to_v3(monkeypatch):
    from src.api.routers import agent_v2 as router_mod

    calls = []

    async def spy(**kwargs):
        calls.append(kwargs)
        return _fake_stream(**kwargs)

    monkeypatch.setattr(v3_runtime, "start_buffered_agent_resume", spy)
    app = _make_app(router_mod)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post(
            "/v2/agent/resume",
            json={"thread_id": "t1", "decision": "approve", "tool": "generate_report"},
        )
    assert resp.status_code == 200
    assert calls and calls[0]["thread_id"] == "t1" and calls[0]["decision"] == "approve"


async def test_cancel_delegates_to_v3(monkeypatch):
    from src.api.routers import agent_v2 as router_mod

    calls = []

    def spy(thread_id):
        calls.append(thread_id)
        return True

    monkeypatch.setattr(v3_runtime, "request_cancel", spy)
    app = _make_app(router_mod)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/v2/agent/cancel", json={"thread_id": "t1"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "cancelled"}
    assert calls == ["t1"]


async def test_status_delegates_to_v3(monkeypatch):
    from src.api.routers import agent_v2 as router_mod

    calls = []

    def spy(thread_id):
        calls.append(thread_id)
        return {"exists": True, "active": True, "last_seq": 3}

    monkeypatch.setattr(v3_runtime, "get_buffered_run_status", spy)
    app = _make_app(router_mod)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/v2/agent/runs/t1")
    assert resp.status_code == 200
    assert resp.json() == {"exists": True, "active": True, "last_seq": 3}
    assert calls == ["t1"]


async def test_attach_delegates_to_v3(monkeypatch):
    from src.api.routers import agent_v2 as router_mod

    calls = []

    def spy(thread_id, after=0):
        calls.append((thread_id, after))
        return _fake_stream()

    monkeypatch.setattr(v3_runtime, "attach_buffered_agent_run", spy)
    app = _make_app(router_mod)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/v2/agent/runs/t1/stream?after=2")
    assert resp.status_code == 200
    assert calls == [("t1", 2)]


async def test_attach_returns_404_when_run_missing(monkeypatch):
    from src.api.routers import agent_v2 as router_mod

    monkeypatch.setattr(v3_runtime, "attach_buffered_agent_run", lambda thread_id, after=0: None)
    app = _make_app(router_mod)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/v2/agent/runs/t1/stream")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "运行任务不存在或已过期"}
