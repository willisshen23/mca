from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.schemas import SkillCategoryCreate, SkillCreate, SkillUpdate
from src.infrastructure.db.session import get_db
from src.services.skill_service import (
    create_category,
    create_skill,
    delete_category,
    delete_skill,
    list_categories,
    list_skills,
    serialize_category,
    serialize_skill,
    update_skill,
    update_skill_category,
)

logger = logging.getLogger("njbank.agent")

router = APIRouter()


@router.get("/skills")
async def api_list_skills(
    category_id: int | None = Query(default=None),
    keyword: str = Query(default=""),
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    skills = list_skills(db, category_id=category_id, keyword=keyword)
    logger.info(
        "skill_api list_skills category_id=%s keyword=%r count=%d cost_ms=%.2f",
        category_id,
        keyword,
        len(skills),
        (time.perf_counter() - started) * 1000,
    )
    return {"skills": [serialize_skill(skill) for skill in skills]}


@router.post("/skills", status_code=201)
async def api_create_skill(body: SkillCreate, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        skill = create_skill(
            db,
            name=body.name,
            template=body.template,
            category_id=body.category_id,
            category_name=body.category_name,
            description=body.description,
        )
    except ValueError as exc:
        logger.warning(
            "skill_api create_skill invalid name=%r category_id=%s category_name=%r",
            body.name,
            body.category_id,
            body.category_name,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "skill_api create_skill id=%s name=%r category_id=%s cost_ms=%.2f",
        skill.id,
        skill.name,
        skill.category_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"skill": serialize_skill(skill)}


@router.patch("/skills/{skill_id}")
async def api_update_skill(skill_id: int, body: SkillUpdate, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        skill = update_skill(
            db,
            skill_id=skill_id,
            name=body.name,
            template=body.template,
            category_id=body.category_id,
            category_name=body.category_name or "",
            description=body.description,
        )
    except ValueError as exc:
        logger.warning("skill_api update_skill invalid skill_id=%s", skill_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "skill_api update_skill id=%s cost_ms=%.2f",
        skill_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"skill": serialize_skill(skill)}


@router.delete("/skills/{skill_id}")
async def api_delete_skill(skill_id: int, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        delete_skill(db, skill_id)
    except ValueError as exc:
        logger.warning("skill_api delete_skill invalid skill_id=%s", skill_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "skill_api delete_skill id=%s cost_ms=%.2f",
        skill_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"status": "deleted"}


@router.get("/skill-categories")
async def api_list_skill_categories(db: Session = Depends(get_db)):
    started = time.perf_counter()
    categories = list_categories(db)
    logger.info(
        "skill_api list_categories count=%d cost_ms=%.2f",
        len(categories),
        (time.perf_counter() - started) * 1000,
    )
    return {"categories": [serialize_category(category) for category in categories]}


@router.post("/skill-categories", status_code=201)
async def api_create_skill_category(body: SkillCategoryCreate, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        category = create_category(db, body.name, body.description)
    except ValueError as exc:
        logger.warning("skill_api create_category invalid name=%r", body.name)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "skill_api create_category id=%s name=%r cost_ms=%.2f",
        category.id,
        category.name,
        (time.perf_counter() - started) * 1000,
    )
    return {"category": serialize_category(category)}


@router.delete("/skill-categories/{category_id}")
async def api_delete_skill_category(category_id: int, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        delete_category(db, category_id)
    except ValueError as exc:
        logger.warning("skill_api delete_category category_id=%s", category_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "skill_api delete_category id=%s cost_ms=%.2f",
        category_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"status": "deleted"}


@router.patch("/skills/{skill_id}/category")
async def api_update_skill_category(skill_id: int, category_id: int, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        skill = update_skill_category(db, skill_id, category_id)
    except ValueError as exc:
        logger.warning("skill_api update_skill_category skill_id=%s category_id=%s", skill_id, category_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "skill_api update_skill_category skill_id=%s category_id=%s cost_ms=%.2f",
        skill_id,
        category_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"skill": serialize_skill(skill)}
