from __future__ import annotations

from fastapi import APIRouter

from src.domain.components import ComponentRegistry

router = APIRouter()


@router.get("/components")
async def list_components():
    return {"components": ComponentRegistry.list_all()}
