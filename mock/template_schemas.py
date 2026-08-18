"""Pydantic schemas for activity template data."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ActivityTemplate(BaseModel):
    """活动模板信息模型（精简字段）."""

    template_id: str = Field(
        ..., alias="projNo", description="模板编号/ID"
    )
    template_name: str = Field(
        ..., alias="projName", description="模板名称"
    )
    template_desc: Optional[str] = Field(
        default="", alias="projDesc", description="模板描述"
    )


class ActivityTemplateListResponse(BaseModel):
    """活动模板列表响应模型."""

    total: int = Field(description="模板总数")
    templates: list[ActivityTemplate] = Field(description="模板列表")
