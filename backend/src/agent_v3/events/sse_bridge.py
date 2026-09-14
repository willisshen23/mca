"""agent-core 流帧 → SSE 帧桥接（帧契约与 v2 完全一致，前端零改动）。"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Callable

from openjiuwen.core.runner import Runner
from openjiuwen.core.session.stream.base import BaseStreamMode, CustomSchema, OutputSchema

from src.agent_v3.events._frames import (
    _args_summary, _compact_report_context, _export_artifact, _frame,
    pipeline_step_frame, tool_progress_frame,
)
from src.agent_v3.approval_wording import generate_approval_wording
from src.agent_v3.tools import TOOL_DISPLAY_NAMES
from src.agent_v3.tools.impl.common import activity_key, activity_name
from src.agent_v3 import sessions as v3_sessions

logger = logging.getLogger("activity-analysis.agent")

_STREAM_MODES = [BaseStreamMode.OUTPUT, BaseStreamMode.CUSTOM]


def _llm_content(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("content") or "")
    if isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[1], dict):
        return str(payload[1].get("content") or "")
    return ""


def _interaction_to_approval_message(payload: Any, thread_id: str) -> dict:
    """__interaction__ 帧 payload → approval_required 消息（对齐 v2 帧结构）。

    真实帧结构（handler.build_interrupt_result 源码确认）：
    OutputSchema.payload = InteractionOutput(id=<interrupt_id>, value=ToolCallInterruptRequest)
    —— 请求内容在 InteractionOutput.value（不是 .payload）。
    """
    request = getattr(payload, "value", None)
    if request is None:
        request = getattr(payload, "payload", None)
    tool = str(getattr(request, "tool_name", "") or "")
    raw_args = getattr(request, "tool_args", None)
    args: dict = {}
    if isinstance(raw_args, dict):
        args = raw_args
    elif isinstance(raw_args, str) and raw_args.strip():
        try:
            args = json.loads(raw_args)
        except (TypeError, ValueError):
            args = {}
    activities = []
    ids = args.get("activity_ids") or []
    if ids:
        # 审批卡片需要可读的活动名称/行号：优先最近查询快照；报告页"追加活动"
        # 场景下原报告的活动不一定在快照里，用当前报告的 data_snapshot 兜底。
        state = v3_sessions.read_business_state(thread_id)
        by_id = {
            activity_key(item): item
            for item in state["activity_list"]
            if isinstance(item, dict)
        }
        snapshot = (state.get("report_context") or {}).get("data_snapshot") or {}
        for aid, name in zip(snapshot.get("activity_ids") or [],
                             snapshot.get("activity_names") or []):
            if aid and str(aid) not in by_id:
                by_id[str(aid)] = {"activity_id": str(aid), "name": name}
        activities = [
            {
                "activity_id": aid,
                "name": activity_name(by_id.get(aid)) if by_id.get(aid) else aid,
                "row_number": (by_id.get(aid, {}) or {}).get("row_number"),
            }
            for aid in ids
        ]
    message = {
        "type": "approval_required",
        "payload": {
            "tool": tool,
            "args": args,
            "description": str(getattr(request, "message", "") or ""),
            "allowed_decisions": ["approve", "edit", "reject"],
            "display_name": TOOL_DISPLAY_NAMES.get(tool, tool),
            "activities": activities,
        },
    }
    return message


def interaction_to_approval_frame(payload: Any, thread_id: str) -> str:
    return _frame(_interaction_to_approval_message(payload, thread_id))


#: 审批话术 LLM 调用超时（秒）：超时/失败回退模板文案，弹窗不被阻塞
_WORDING_TIMEOUT_S = 5.0


async def _approval_frame_with_wording(payload: Any, thread_id: str) -> str:
    """审批帧 + LLM 确认话术：话术替换副标题（description），
    正文（活动列表/参数）保持确定性渲染。"""
    message = _interaction_to_approval_message(payload, thread_id)
    frame_payload = message["payload"]
    try:
        wording = await asyncio.wait_for(
            generate_approval_wording(
                tool_display=frame_payload["display_name"],
                args_summary=_args_summary(frame_payload["args"]),
                activity_names=[a["name"] for a in frame_payload["activities"]],
                overwrite=(frame_payload["tool"] == "generate_report" and bool(
                    v3_sessions.read_business_state(thread_id).get("html_report"))),
            ),
            timeout=_WORDING_TIMEOUT_S,
        )
    except Exception:
        wording = ""
    if wording:
        frame_payload["description"] = wording
    return _frame(message)


#: 取消轮询粒度（秒）：长 LLM 调用期间流内无帧，靠泵+超时轮询让取消即时生效
_CANCEL_POLL_INTERVAL_S = 0.5

_STREAM_END = object()


async def stream_v3_events(
    agent,
    session,
    inputs: dict,
    request_id: str,
    thread_id: str,
    is_cancelled: Callable[[], bool],
) -> AsyncGenerator[str, None]:
    """驱动 Runner.run_agent_streaming 并产出 SSE 帧（帧契约同 v2）。

    取消语义：泵任务把流帧搬入队列，主循环以 _CANCEL_POLL_INTERVAL_S 超时轮询，
    即使工具内长 LLM 调用期间无帧，取消也能在轮询粒度内生效；退出时取消泵
    （把 CancelledError 传播进在途的 LLM 调用）并关闭流生成器。
    """
    answer_output = ""
    accumulated: list[str] = []
    saw_interrupt = False
    report_updated = False
    tool_calls_count = 0
    export_succeeded = False
    export_artifact: dict = {}
    cancelled = False

    agen = Runner.run_agent_streaming(agent, inputs, session=session,
                                      stream_modes=_STREAM_MODES)
    queue: asyncio.Queue = asyncio.Queue()

    async def _pump() -> None:
        try:
            async for chunk in agen:
                await queue.put(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 框架异常透传主循环统一处理
            await queue.put(exc)
        finally:
            await queue.put(_STREAM_END)

    pump = asyncio.create_task(_pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(),
                                              timeout=_CANCEL_POLL_INTERVAL_S)
            except asyncio.TimeoutError:
                if is_cancelled():
                    cancelled = True
                    break
                continue
            if item is _STREAM_END:
                break
            if isinstance(item, Exception):
                raise item
            if is_cancelled():
                cancelled = True
                break
            chunk = item

            if isinstance(chunk, CustomSchema):
                data = chunk.model_dump()
                marker = data.pop("activity-analysis", None)
                if marker == "tool_progress":
                    tool = str(data.get("tool") or "")
                    status = str(data.get("status") or "")
                    if status == "running":
                        tool_calls_count += 1
                    if tool == "export_report" and status == "done" \
                            and not str(data.get("summary") or "").startswith("ERROR:"):
                        export_succeeded = True
                    if tool in {"generate_report", "modify_report"} and status == "done":
                        report_updated = True
                    yield tool_progress_frame(tool, status,
                                              summary=str(data.get("summary") or ""),
                                              args_summary=data.get("args_summary") or None)
                elif marker == "state_update":
                    state_data = dict(data.get("data") or {})
                    if "report_html_guard_result" in state_data:
                        report_updated = True
                    formatted = state_data.pop("formatted_output_path", None)
                    if formatted and export_succeeded:
                        artifact = _export_artifact(formatted)
                        if artifact:
                            export_artifact = artifact
                            state_data["export_artifact"] = artifact
                    if state_data:
                        yield _frame({"type": "node_update", "payload": state_data})
                elif "step" in data:
                    step_payload = data.get("payload")
                    yield pipeline_step_frame(str(data.get("step")),
                                              str(data.get("status") or "running"),
                                              payload=step_payload if isinstance(step_payload, dict) else None)
                continue

            if not isinstance(chunk, OutputSchema):
                continue

            if chunk.type == "llm_output":
                accumulated.append(_llm_content(chunk.payload))
            elif chunk.type == "answer":
                payload = chunk.payload if isinstance(chunk.payload, dict) else {}
                # 框架 stream_process 吞掉 invoke 异常后以 answer 帧下发
                # {"output": str(e), "result_type": "error"}。若当正常 answer
                # 发 done，turn 会被记成 success：用户看到假回复，且本轮 context
                # 从未落库（checkpoint 只剩空 context），之后每轮都被模型当成
                # 第一个问题。必须抛出，走 runtime 失败路径（记 failed + error 帧）。
                if str(payload.get("result_type") or "") == "error":
                    error_text = str(payload.get("output") or "agent 执行失败")
                    logger.error(
                        "agent_v3 框架吞掉的执行异常（answer result_type=error）: "
                        "thread=%s request=%s error=%s",
                        thread_id, request_id, error_text,
                    )
                    raise RuntimeError(error_text)
                answer_output = str(payload.get("output") or "")
            elif chunk.type == "__interaction__":
                saw_interrupt = True
                interrupt_id = str(getattr(chunk.payload, "id", "") or "")
                if interrupt_id:
                    v3_sessions.set_pending_interrupt(thread_id, interrupt_id)
                yield await _approval_frame_with_wording(chunk.payload, thread_id)
            # llm_reasoning / llm_usage / tracer_*：忽略
    finally:
        pump.cancel()
        try:
            await pump
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await agen.aclose()
        except Exception:
            pass

    if cancelled:
        yield _frame({"type": "cancelled", "payload": {}})
        return

    business = v3_sessions.read_business_state(thread_id)
    if export_succeeded and not export_artifact:
        export_artifact = _export_artifact(business.get("formatted_output_path"))
    yield _frame({
        "type": "done",
        "payload": {
            "request_id": request_id,
            "final_response": answer_output or "".join(accumulated),
            "html_report": business["html_report"],
            "analysis_queue": business["analysis_queue"],
            "report_context": _compact_report_context(business["report_context"]),
            "export_artifact": export_artifact,
            "report_updated": report_updated,
            "awaiting_approval": saw_interrupt,
            "tool_calls_count": tool_calls_count,
        },
    })
