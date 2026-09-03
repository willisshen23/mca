from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.schemas import SystemPromptCreate, SystemPromptPublish, SystemPromptUpdate
from src.infrastructure.db.session import get_db
from src.services.system_prompt_service import (
    create_system_prompt,
    get_prompt,
    get_prompt_by_key,
    list_system_prompts,
    publish_system_prompt,
    serialize_system_prompt,
    update_system_prompt,
    validate_prompt_variables,
)

logger = logging.getLogger("activity-analysis.agent")

router = APIRouter(prefix="/system-prompts")


@router.get("")
async def api_list_system_prompts(
    status: str = Query(default=""),
    keyword: str = Query(default=""),
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    try:
        prompts = list_system_prompts(db, status=status, keyword=keyword)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "system_prompt_api list status=%r keyword=%r count=%d cost_ms=%.2f",
        status,
        keyword,
        len(prompts),
        (time.perf_counter() - started) * 1000,
    )
    return {"prompts": [serialize_system_prompt(prompt) for prompt in prompts]}


@router.get("/key/{prompt_key}")
async def api_get_system_prompt_by_key(prompt_key: str, db: Session = Depends(get_db)):
    prompt = get_prompt_by_key(db, prompt_key)
    if prompt is None:
        raise HTTPException(status_code=404, detail="系统提示词不存在")
    return {"prompt": serialize_system_prompt(prompt)}


@router.get("/{prompt_id}")
async def api_get_system_prompt(prompt_id: int, db: Session = Depends(get_db)):
    try:
        prompt = get_prompt(db, prompt_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"prompt": serialize_system_prompt(prompt)}


@router.post("", status_code=201)
async def api_create_system_prompt(body: SystemPromptCreate, db: Session = Depends(get_db)):
    started = time.perf_counter()
    try:
        prompt = create_system_prompt(
            db,
            prompt_key=body.prompt_key,
            prompt_name=body.prompt_name,
            agent_name=body.agent_name,
            scenario=body.scenario,
            content=body.content,
            variables=body.variables,
            status=body.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "system_prompt_api create id=%s key=%s cost_ms=%.2f",
        prompt.id,
        prompt.prompt_key,
        (time.perf_counter() - started) * 1000,
    )
    return {"prompt": serialize_system_prompt(prompt)}


@router.patch("/{prompt_id}")
async def api_update_system_prompt(
    prompt_id: int,
    body: SystemPromptUpdate,
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    try:
        prompt = update_system_prompt(
            db,
            prompt_id,
            prompt_name=body.prompt_name,
            agent_name=body.agent_name,
            scenario=body.scenario,
            content=body.content,
            variables=body.variables,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "system_prompt_api update id=%s key=%s status=%s cost_ms=%.2f",
        prompt.id,
        prompt.prompt_key,
        prompt.status,
        (time.perf_counter() - started) * 1000,
    )
    return {"prompt": serialize_system_prompt(prompt)}


@router.post("/{prompt_id}/publish")
async def api_publish_system_prompt(
    prompt_id: int,
    body: SystemPromptPublish | None = None,
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    try:
        prompt = publish_system_prompt(db, prompt_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "system_prompt_api publish id=%s key=%s note=%r cost_ms=%.2f",
        prompt.id,
        prompt.prompt_key,
        (body.change_note if body else ""),
        (time.perf_counter() - started) * 1000,
    )
    return {
        "prompt": serialize_system_prompt(prompt),
        "missing_variables": validate_prompt_variables(prompt.content, serialize_system_prompt(prompt)["variables"]),
    }
