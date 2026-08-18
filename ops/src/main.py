from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import load_settings
from src.diagnosis.pipeline import followup, run_diagnosis
from src.inspection import run_inspection, scheduler_loop
from src.rules.engine import load_rules
from src.storage import OpsDB

logger = logging.getLogger("ops.main")

_OPS_DIR = Path(__file__).resolve().parents[1]
_RULES_PATH = Path(__file__).resolve().parent / "rules" / "rules.yaml"
_STATIC_DIR = _OPS_DIR / "web" / "static"


class DiagnoseRequest(BaseModel):
    check_id: str


class FollowupRequest(BaseModel):
    question: str


class RunbookRequest(BaseModel):
    slug: str
    title: str
    category: str
    body: str


class RunbookUpdateRequest(BaseModel):
    title: str
    category: str
    body: str


def create_app(settings=None, db=None) -> FastAPI:
    settings = settings or load_settings()
    if db is None:
        db = OpsDB(settings.ops_db_path)
        db.init()
    db.seed_runbooks(settings.seed_runbook_dir)
    rules = load_rules(_RULES_PATH)

    @asynccontextmanager
    async def lifespan(app):
        stop_event = asyncio.Event()
        task = asyncio.create_task(scheduler_loop(settings, db, rules, stop_event))
        yield
        stop_event.set()
        task.cancel()

    app = FastAPI(title="ops-assistant", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db

    def require_token(request: Request) -> None:
        if settings.ops_token and request.headers.get("X-Ops-Token") != settings.ops_token:
            raise HTTPException(status_code=401, detail="无效访问令牌")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/inspections/latest", dependencies=[Depends(require_token)])
    async def latest():
        snapshot = db.latest_snapshot()
        if snapshot is None:
            return {"overall": "gray", "checks": [], "message": "尚未巡检"}
        return snapshot

    @app.get("/api/inspections/history", dependencies=[Depends(require_token)])
    async def history(limit: int = 50):
        return db.list_snapshots(limit)

    @app.post("/api/inspections/run", dependencies=[Depends(require_token)])
    async def run_now():
        return await run_inspection(settings, db, rules)

    @app.post("/api/diagnoses", dependencies=[Depends(require_token)])
    async def diagnose(req: DiagnoseRequest):
        return await run_diagnosis(db, settings, req.check_id)

    @app.get("/api/diagnoses/{diagnosis_id}", dependencies=[Depends(require_token)])
    async def diagnosis_detail(diagnosis_id: int):
        diag = db.get_diagnosis(diagnosis_id)
        if diag is None:
            raise HTTPException(status_code=404, detail="诊断记录不存在")
        diag["conclusion"] = json.loads(diag["conclusion"])
        diag["transcript"] = json.loads(diag["transcript"])
        return diag

    @app.post("/api/diagnoses/{diagnosis_id}/followup", dependencies=[Depends(require_token)])
    async def diagnosis_followup(diagnosis_id: int, req: FollowupRequest):
        try:
            return await followup(db, settings, diagnosis_id, req.question)
        except KeyError:
            raise HTTPException(status_code=404, detail="诊断记录不存在") from None

    @app.get("/api/runbooks", dependencies=[Depends(require_token)])
    async def runbook_list():
        return db.list_runbooks()

    @app.get("/api/runbooks/{slug}", dependencies=[Depends(require_token)])
    async def runbook_detail(slug: str):
        runbook = db.get_runbook(slug)
        if runbook is None:
            raise HTTPException(status_code=404, detail="runbook 不存在")
        return runbook

    @app.post("/api/runbooks", dependencies=[Depends(require_token)])
    async def runbook_create(req: RunbookRequest):
        db.upsert_runbook(req.slug, req.title, req.category, req.body)
        return {"slug": req.slug}

    @app.put("/api/runbooks/{slug}", dependencies=[Depends(require_token)])
    async def runbook_update(slug: str, req: RunbookUpdateRequest):
        if db.get_runbook(slug) is None:
            raise HTTPException(status_code=404, detail="runbook 不存在")
        db.upsert_runbook(slug, req.title, req.category, req.body)
        return {"slug": slug}

    if _STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")

    return app


app = create_app()
