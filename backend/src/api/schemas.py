from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class AnalysisComponentRequest(BaseModel):
    id: str
    type: str
    title: str
    config: dict = Field(default_factory=dict)


class AnalysisFrameworkRequest(BaseModel):
    title: str = ""
    components: list[AnalysisComponentRequest] = Field(default_factory=list)
    report_config: dict = Field(default_factory=dict)


class AnalyzeRequest(BaseModel):
    thread_id: str
    file_path: str = ""
    message: str = ""
    original_user_text: str = ""
    framework: AnalysisFrameworkRequest = Field(default_factory=AnalysisFrameworkRequest)
    target_format: str = ""
    selected_activity_ids: list[str] = Field(default_factory=list)
    user_id: str = ""
    org_no: str = ""
    channel: str = ""


class UploadResponse(BaseModel):
    file_id: str
    file_name: str
    file_path: str
    preview: dict
    message: str


class CancelRequest(BaseModel):
    thread_id: str


class SSEMessage(BaseModel):
    type: str
    payload: dict


class SkillCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


class SkillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category_id: int | None = None
    category_name: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=500)
    template: str = Field(min_length=1)


class SkillUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    category_id: Optional[int] = None
    category_name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    template: Optional[str] = Field(default=None, min_length=1)


class ActivityTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: str = Field(default="通用", max_length=40)
    description: str = Field(min_length=1, max_length=500)
    skills: list[str] = Field(default_factory=list)


class ActivityTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    type: Optional[str] = Field(default=None, max_length=40)
    description: Optional[str] = Field(default=None, min_length=1, max_length=500)
    skills: Optional[list[str]] = None


class SystemPromptCreate(BaseModel):
    prompt_key: str = Field(min_length=1, max_length=120)
    prompt_name: str = Field(min_length=1, max_length=160)
    agent_name: str = Field(min_length=1, max_length=80)
    scenario: str = Field(default="", max_length=80)
    content: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)
    status: str = Field(default="pending", max_length=20)


class SystemPromptUpdate(BaseModel):
    prompt_name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    agent_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    scenario: Optional[str] = Field(default=None, max_length=80)
    content: Optional[str] = Field(default=None, min_length=1)
    variables: Optional[list[str]] = None


class SystemPromptPublish(BaseModel):
    change_note: str = Field(default="", max_length=500)


class EnvConfigUpdate(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)
    content: Optional[str] = None


class QuickPromptItem(BaseModel):
    id: int
    text: str = Field(min_length=1, max_length=500)
    sort_order: int
    is_enabled: bool


class QuickPromptSaveItem(BaseModel):
    id: int | None = None
    text: str = Field(min_length=1, max_length=500)
    is_enabled: bool = True


class QuickPromptListResponse(BaseModel):
    prompts: list[str]


class QuickPromptAdminListResponse(BaseModel):
    prompts: list[QuickPromptItem]


class ReportFeedbackUpdate(BaseModel):
    feedback: str = Field(min_length=1, max_length=16)
    user_id: str = Field(default="", max_length=64)
    version_no: int | None = None
    comment: str | None = None
