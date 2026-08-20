"""agent API 路由：/api/v2/agent/*（URL 前缀保留，前端契约；内部无条件走 agent_v3）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agent_v3 import runtime as v3_runtime

router = APIRouter(prefix="/v2/agent")


class AgentRunRequest(BaseModel):
    thread_id: str
    message: str
    original_user_text: str = ""
    file_path: str = ""
    user_id: str = ""
    user_name: str = ""
    org_no: str = ""
    src_sys_no: str = ""
    channel: str = ""
    # 报告页组件编排预选的分析组件（[{name, cat, desc, tpl}]），/chat-ui 不传
    report_components: list[dict] = []


class AgentCancelRequest(BaseModel):
    thread_id: str


@router.post("/run")
async def run(body: AgentRunRequest):
    kwargs = dict(
        thread_id=body.thread_id,
        message=body.message,
        original_user_text=body.original_user_text,
        file_path=body.file_path,
        user_id=body.user_id,
        user_name=body.user_name,
        org_no=body.org_no,
        src_sys_no=body.src_sys_no,
        channel=body.channel,
        report_components=body.report_components,
    )
    stream = await v3_runtime.start_buffered_agent_run(**kwargs)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
    )


@router.get("/runs/{thread_id}")
async def run_status(thread_id: str):
    return v3_runtime.get_buffered_run_status(thread_id)


@router.get("/runs/{thread_id}/stream")
async def attach_run(thread_id: str, after: int = Query(default=0, ge=0)):
    stream = v3_runtime.attach_buffered_agent_run(thread_id, after=after)
    if stream is None:
        raise HTTPException(status_code=404, detail="运行任务不存在或已过期")
    return StreamingResponse(stream, media_type="text/event-stream")


@router.post("/cancel")
async def cancel(body: AgentCancelRequest):
    cancelled = v3_runtime.request_cancel(body.thread_id)
    return {"status": "cancelled" if cancelled else "not_found"}


class AgentResumeRequest(BaseModel):
    thread_id: str
    decision: str
    tool: str = ""
    edited_args: dict = {}
    message: str = ""
    user_id: str = ""
    user_name: str = ""
    org_no: str = ""
    src_sys_no: str = ""
    channel: str = ""


@router.post("/resume")
async def resume(body: AgentResumeRequest):
    kwargs = dict(
        thread_id=body.thread_id,
        decision=body.decision,
        tool=body.tool,
        edited_args=body.edited_args,
        message=body.message,
        user_id=body.user_id,
        user_name=body.user_name,
        org_no=body.org_no,
        src_sys_no=body.src_sys_no,
        channel=body.channel,
    )
    stream = await v3_runtime.start_buffered_agent_resume(**kwargs)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
    )
