from __future__ import annotations

from fastapi import APIRouter

from . import (
    activity_templates,
    agent_run_history,
    agent_v2,
    components,
    conversation_logs,
    conversations,
    env_config,
    files,
    logs,
    online_activities,
    quick_prompts,
    reports,
    skills,
    system_prompts,
    usage_dashboard,
)


def create_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(files.router)
    router.include_router(reports.router)
    router.include_router(components.router)
    router.include_router(skills.router)
    router.include_router(activity_templates.router)
    router.include_router(system_prompts.router)
    router.include_router(quick_prompts.router)
    router.include_router(env_config.router)
    router.include_router(conversations.router)
    router.include_router(conversation_logs.router)
    router.include_router(agent_run_history.router)
    router.include_router(logs.router)
    router.include_router(online_activities.router)
    router.include_router(agent_v2.router)
    router.include_router(usage_dashboard.router)
    return router
