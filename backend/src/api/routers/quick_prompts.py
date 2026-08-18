from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.schemas import (
    QuickPromptAdminListResponse,
    QuickPromptItem,
    QuickPromptListResponse,
    QuickPromptSaveItem,
)
from src.infrastructure.db.session import get_db
from src.services.quick_prompt_service import (
    list_all_quick_prompts,
    list_enabled_quick_prompts,
    save_quick_prompts,
)

logger = logging.getLogger("njbank.agent")
router = APIRouter(prefix="/quick-prompts")


class _QuickPromptSaveRequest(BaseModel):
    prompts: list[QuickPromptSaveItem]


@router.get("")
async def api_list_quick_prompts(db: Session = Depends(get_db)) -> QuickPromptListResponse:
    started = time.perf_counter()
    prompts = list_enabled_quick_prompts(db)
    logger.info(
        "quick_prompt_api list enabled count=%d cost_ms=%.2f",
        len(prompts),
        (time.perf_counter() - started) * 1000,
    )
    return QuickPromptListResponse(prompts=prompts)


@router.get("/admin")
async def api_list_admin_quick_prompts(db: Session = Depends(get_db)) -> QuickPromptAdminListResponse:
    rows = list_all_quick_prompts(db)
    return QuickPromptAdminListResponse(
        prompts=[
            QuickPromptItem(
                id=row.id,
                text=row.text,
                sort_order=row.sort_order,
                is_enabled=row.is_enabled,
            )
            for row in rows
        ]
    )


@router.put("/admin")
async def api_save_admin_quick_prompts(
    body: _QuickPromptSaveRequest,
    db: Session = Depends(get_db),
) -> QuickPromptAdminListResponse:
    started = time.perf_counter()
    try:
        saved = save_quick_prompts(db, [item.model_dump() for item in body.prompts])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "quick_prompt_api save count=%d cost_ms=%.2f",
        len(saved),
        (time.perf_counter() - started) * 1000,
    )
    return QuickPromptAdminListResponse(
        prompts=[
            QuickPromptItem(
                id=row.id,
                text=row.text,
                sort_order=row.sort_order,
                is_enabled=row.is_enabled,
            )
            for row in saved
        ]
    )
