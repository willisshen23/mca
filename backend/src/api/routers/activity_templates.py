from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.schemas import ActivityTemplateCreate, ActivityTemplateUpdate
from src.infrastructure.db.session import get_db
from src.services.activity_template_service import (
    create_template,
    delete_template,
    increment_template_usage,
    list_templates,
    serialize_template,
    update_template,
)
from src.services.skill_service import record_skill_component_usage

logger = logging.getLogger("activity-analysis.agent")

router = APIRouter(prefix="/activity-templates")


@router.get("")
async def api_list_activity_templates(
    type: str = Query(default=""),
    keyword: str = Query(default=""),
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    templates = list_templates(db, template_type=type, keyword=keyword)
    logger.info(
        "template_api list_templates type=%r keyword=%r count=%d cost_ms=%.2f",
        type,
        keyword,
        len(templates),
        (time.perf_counter() - started) * 1000,
    )
    return {"templates": [serialize_template(template) for template in templates]}


@router.post("", status_code=201)
async def api_create_activity_template(
    body: ActivityTemplateCreate,
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    try:
        template = create_template(
            db,
            name=body.name,
            template_type=body.type,
            description=body.description,
            skills=body.skills,
        )
    except ValueError as exc:
        logger.warning("template_api create_template invalid name=%r", body.name)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "template_api create_template id=%s name=%r cost_ms=%.2f",
        template.id,
        template.name,
        (time.perf_counter() - started) * 1000,
    )
    return {"template": serialize_template(template)}


@router.patch("/{template_id}")
async def api_update_activity_template(
    template_id: int,
    body: ActivityTemplateUpdate,
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    try:
        template = update_template(
            db,
            template_id=template_id,
            name=body.name,
            template_type=body.type,
            description=body.description,
            skills=body.skills,
        )
    except ValueError as exc:
        logger.warning("template_api update_template invalid id=%s", template_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "template_api update_template id=%s cost_ms=%.2f",
        template_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"template": serialize_template(template)}


@router.delete("/{template_id}")
async def api_delete_activity_template(template_id: int, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        delete_template(db, template_id)
    except ValueError as exc:
        logger.warning("template_api delete_template invalid id=%s", template_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "template_api delete_template id=%s cost_ms=%.2f",
        template_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"status": "deleted"}


@router.post("/{template_id}/apply")
async def api_apply_activity_template(template_id: int, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        template = increment_template_usage(db, template_id)
    except ValueError as exc:
        logger.warning("template_api apply_template invalid id=%s", template_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        try:
            skill_names = json.loads(template.skills_json or "[]")
        except json.JSONDecodeError:
            skill_names = []
        record_skill_component_usage(
            skill_names if isinstance(skill_names, list) else [],
            source_type="activity_template",
            source_id=template.id,
            source_code=template.code,
            scene="activity_analysis",
        )
    except Exception as exc:
        logger.warning("template_api apply_template skill usage failed id=%s error=%s", template_id, exc)
    logger.info(
        "template_api apply_template id=%s cost_ms=%.2f",
        template_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"template": serialize_template(template)}
