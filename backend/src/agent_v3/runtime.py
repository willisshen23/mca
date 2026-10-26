"""agent_v3 运行时：请求驱动、取消注册表、审计（契约与 v2 runtime 完全一致）。

镜像 agent_v2/runtime.py 的契约：
- 同一 thread_id 同时仅一个活跃 run（经 _cancelled 注册表约束）；
- 取消在流事件间隙生效（与 v2 同粒度，bridge 在帧间隙检查 is_cancelled）；
- turn 级审计经 conversation_log_service（record_turn_start/finish_turn）；
- 审批恢复经 openJiuwen InteractiveInput（interrupt_id → payload），
  新一轮 __interaction__ 由 sse_bridge 自动登记新 pending id，天然支持二次审批。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import AsyncGenerator
from uuid import uuid4

from openjiuwen.core.session import InteractiveInput

from src.agent_v3 import sessions as v3_sessions
from src.agent_v3.agent_factory import get_v3_agent
from src.agent_v3.events.sse_bridge import stream_v3_events
from src.agent_v3.request_context import (
    reset_request_context,
    set_request_context,
)
from src.services.conversation_log_service import finish_turn, record_turn_start

logger = logging.getLogger("activity-analysis.agent")

_cancelled: dict[str, asyncio.Event] = {}

# ── 以下整段从 agent_v2/runtime.py 平移（_BufferedRun/缓冲注册表/取消/帧函数）──


@dataclass
class _BufferedRun:
    """A run that outlives any individual browser streaming connection."""

    thread_id: str
    frames: list[str] = field(default_factory=list)
    done: bool = False
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task | None = None

    async def publish(self, frame_text: str) -> None:
        async with self.condition:
            self.frames.append(frame_text)
            self.condition.notify_all()

    async def finish(self) -> None:
        async with self.condition:
            self.done = True
            self.condition.notify_all()

    async def stream(self, after: int = 0) -> AsyncGenerator[str, None]:
        cursor = max(0, min(after, len(self.frames)))
        while True:
            async with self.condition:
                await self.condition.wait_for(lambda: cursor < len(self.frames) or self.done)
                pending = self.frames[cursor:]
                finished = self.done

            for frame_text in pending:
                cursor += 1
                yield f"id: {cursor}\n{frame_text}"

            if finished and cursor >= len(self.frames):
                return


_buffered_runs: dict[str, _BufferedRun] = {}
_buffered_runs_lock = asyncio.Lock()


async def _expire_buffered_run(run: _BufferedRun) -> None:
    await asyncio.sleep(300)
    async with _buffered_runs_lock:
        if _buffered_runs.get(run.thread_id) is run:
            _buffered_runs.pop(run.thread_id, None)


async def _drive_buffered_run(
    run: _BufferedRun,
    source: AsyncGenerator[str, None],
) -> None:
    try:
        async for frame_text in source:
            await run.publish(frame_text)
    finally:
        await run.finish()
        asyncio.create_task(_expire_buffered_run(run))


async def _start_buffered_run(
    thread_id: str,
    source: AsyncGenerator[str, None],
    replace: bool = False,
) -> AsyncGenerator[str, None]:
    async with _buffered_runs_lock:
        existing = _buffered_runs.get(thread_id)
        if existing and not existing.done and not replace:
            await source.aclose()

            async def conflict_stream() -> AsyncGenerator[str, None]:
                yield _frame("error", {"message": "该会话已有正在运行的任务，请先停止或等待完成"})

            return conflict_stream()

        run = _BufferedRun(thread_id=thread_id)
        _buffered_runs[thread_id] = run
        run.task = asyncio.create_task(_drive_buffered_run(run, source))
        return run.stream()


async def start_buffered_agent_run(**kwargs) -> AsyncGenerator[str, None]:
    """Start a detached run and return a replayable stream from its first frame."""
    return await _start_buffered_run(
        kwargs["thread_id"],
        stream_agent_run(**kwargs),
    )


async def start_buffered_agent_resume(**kwargs) -> AsyncGenerator[str, None]:
    """Resume an approval in a detached, replayable run."""
    return await _start_buffered_run(
        kwargs["thread_id"],
        stream_agent_resume(**kwargs),
    )


async def start_buffered_agent_steer(**kwargs) -> AsyncGenerator[str, None]:
    """Start a steer run (打断当前任务并带插话续跑) in a detached, replayable run.

    与 run/resume 不同：调用时该 thread 必然有一个活跃 run（否则 steer
    无意义），故用 replace=True 直接接管缓冲槽位；旧 run 的缓冲对象仍由
    自己的驱动任务收尾（_expire_buffered_run 按身份比对，不会误删新 run）。
    """
    return await _start_buffered_run(
        kwargs["thread_id"],
        stream_agent_steer(**kwargs),
        replace=True,
    )


def get_buffered_run_status(thread_id: str) -> dict:
    # pending_approval 是服务端权威的待决审批状态：缓冲过期/进程重启后
    # 前端 localStorage 里的审批卡片会与服务端失配，前端刷新时凭此字段
    # 作废本地残留卡片，避免输入框被锁死在“等待审批”。
    pending_approval = v3_sessions.get_pending_interrupt(thread_id) is not None
    run = _buffered_runs.get(thread_id)
    if run is None:
        return {"exists": False, "active": False, "last_seq": 0, "pending_approval": pending_approval}
    return {
        "exists": True,
        "active": not run.done,
        "last_seq": len(run.frames),
        "pending_approval": pending_approval,
    }


def attach_buffered_agent_run(thread_id: str, after: int = 0) -> AsyncGenerator[str, None] | None:
    run = _buffered_runs.get(thread_id)
    if run is None:
        return None
    return run.stream(after=after)


def request_cancel(thread_id: str) -> bool:
    event = _cancelled.get(thread_id)
    if event is None:
        return False
    event.set()
    return True


def _frame(event_type: str, payload: dict) -> str:
    import json

    return f"data: {json.dumps({'type': event_type, 'payload': payload}, ensure_ascii=False, default=str)}\n\n"


def _done_frame_final_values(frame_text: str) -> dict:
    """从 done 帧提取终态值（final_response/html_report），供 turn 审计落库。

    finish_turn 的 assistant_response 数据源——会话重载（P2 起业务表驱动）
    依赖 conversation_turn.assistant_response 重建 AI 消息。
    """
    import json

    try:
        data = json.loads(frame_text.split("data: ", 1)[1])
        payload = data.get("payload") or {}
        return {
            "final_response": str(payload.get("final_response") or ""),
            "html_report": str(payload.get("html_report") or ""),
        }
    except Exception:
        return {}


# ── 平移结束；以下为 v3 驱动函数 ──


async def stream_agent_run(
    thread_id: str,
    message: str,
    original_user_text: str = "",
    file_path: str = "",
    user_id: str = "",
    user_name: str = "",
    org_no: str = "",
    src_sys_no: str = "",
    channel: str = "",
    report_components: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    """驱动一轮 v3 对话并产出 SSE 帧。"""
    if thread_id in _cancelled:
        yield _frame("error", {"message": "该会话已有正在运行的任务，请先停止或等待完成"})
        return

    request_id = uuid4().hex
    started = time.monotonic()
    cancel_event = asyncio.Event()
    _cancelled[thread_id] = cancel_event
    ctx_token = set_request_context(
        {
            "user_id": user_id,
            "user_name": user_name,
            "org_no": org_no,
            "src_sys_no": src_sys_no,
            "channel": channel,
            "uploaded_file_path": file_path,
            "thread_id": thread_id,
            "request_id": request_id,
            "original_user_text": original_user_text or message,
            "report_components": list(report_components or []),
            # 本 run 的取消事件。stream_process task 创建时拷贝上下文，旧 run
            # 的管线永远看到自己这一届的 event——插话取消后，报告管线各阶段
            # 据此尽快中止（否则旧管线会在后台跑完全程，多烧 LLM 调用并把
            # 多份报告版本写入数据库）。
            "cancel_event": cancel_event,
        }
    )

    try:
        # 审计 state 的 messages 用 dict 而非旧框架的消息对象：
        # agent_run_history_service._original_user_text 对 dict 消息按
        # role/type ∈ {"human", "user"} 解析（源码已确认），语义与 v2 一致。
        # 同步 SQLite 写放工作线程：pipeline 线程也在写同一库文件，
        # 在事件循环上直接提交可能撞上 busy-timeout 冻结整个服务。
        await asyncio.to_thread(
            record_turn_start,
            {
                "request_id": request_id,
                "thread_id": thread_id,
                "user_id": user_id,
                "user_name": user_name,
                "channel": channel,
                "messages": [{"role": "user", "content": message}],
                "original_user_text": original_user_text or message,
            },
        )

        agent = await get_v3_agent()
        session = v3_sessions.new_run_session(thread_id, card=agent.card)

        # 上下文池隔离：框架把真正的执行放在独立 task（stream_process）里，
        # 外层生成器被 aclose 时被取消的 run 并不会停——它仍在后台续跑，继续
        # 往池里与新 run 共享的上下文对象追加消息。双方交错追加会把历史搅成
        # OpenAI 协议 400（assistant.tool_calls 无配对 tool 结果、user 消息
        # 插在 assistant/tool 之间）。这里把该 thread 的池内上下文摘除成
        # sanitized 快照（旧 run 只污染它自己持有的旧对象），快照经 session
        # state 注入新 run，重建出干净副本。
        context_snapshot = _detach_context_snapshot(agent, thread_id)
        if context_snapshot:
            logger.info("agent_v3 上下文池隔离: thread=%s contexts=%s",
                        thread_id, list(context_snapshot))

        # P2 重启场景：checkpoint 可能残留上一次中断的现场（pending_interrupt
        # 是进程内的，重启后已空）。不作废的话框架会恢复旧中断并把这条新消息
        # 吞掉（不进对话上下文）；同时修补悬空 tool_calls 保证协议完整。
        # 进程内有待决审批时不动——由 /resume 驱动。
        if v3_sessions.get_pending_interrupt(thread_id) is None:
            discarded, repaired = await v3_sessions.prepare_fresh_run_session(
                session, inputs={"query": message})
            if discarded:
                logger.info(
                    "agent_v3 作废 checkpoint 残留中断: thread=%s（审批挂起跨重启，按设计审批作废）",
                    thread_id,
                )
            if repaired:
                logger.info(
                    "agent_v3 修补悬空 tool_calls: thread=%s count=%d",
                    thread_id, repaired,
                )

        if context_snapshot:
            session.update_state({"context": context_snapshot})

        final_status = "success"
        failure_reason = ""
        final_values: dict = {}
        async for frame_text in stream_v3_events(
            agent=agent,
            session=session,
            inputs={"query": message},
            request_id=request_id,
            thread_id=thread_id,
            is_cancelled=cancel_event.is_set,
        ):
            if '"type": "cancelled"' in frame_text:
                final_status = "cancelled"
                failure_reason = "用户取消任务"
            elif '"type": "approval_required"' in frame_text:
                # 审批中断不算完成也不算失败，turn 标记为 awaiting
                final_status = "awaiting_approval"
            elif '"type": "done"' in frame_text:
                final_values = _done_frame_final_values(frame_text)
            yield frame_text

        duration_ms = int((time.monotonic() - started) * 1000)
        await asyncio.to_thread(
            finish_turn,
            request_id,
            final_status,
            duration_ms,
            final_values,
            failure_reason=failure_reason,
        )
        logger.info(
            "agent_v3 run 完成: thread=%s request=%s status=%s cost=%dms",
            thread_id,
            request_id,
            final_status,
            duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.exception("agent_v3 run 异常: thread=%s request=%s", thread_id, request_id)
        await asyncio.to_thread(
            finish_turn, request_id, "failed", duration_ms, failure_reason=str(exc)[:500]
        )
        yield _frame("error", {"message": str(exc)[:300]})
    finally:
        _cancelled.pop(thread_id, None)
        reset_request_context(ctx_token)


async def stream_agent_resume(
    thread_id: str,
    decision: str,
    tool: str = "",
    edited_args: dict | None = None,
    message: str = "",
    user_id: str = "",
    user_name: str = "",
    org_no: str = "",
    src_sys_no: str = "",
    channel: str = "",
) -> AsyncGenerator[str, None]:
    """审批恢复：经 InteractiveInput 驱动 agent-core 从 __interaction__ 继续执行。"""
    if decision not in {"approve", "edit", "reject"}:
        yield _frame("error", {"message": f"无效的审批决策：{decision}"})
        return

    interrupt_id = v3_sessions.get_pending_interrupt(thread_id)
    if not interrupt_id:
        yield _frame("error", {"message": "该会话没有待审批的操作"})
        return

    request_id = uuid4().hex
    started = time.monotonic()
    audit_text = f"已审批 {tool}：{decision}"
    cancel_event = asyncio.Event()
    _cancelled[thread_id] = cancel_event
    ctx_token = set_request_context(
        {
            "user_id": user_id,
            "user_name": user_name,
            "org_no": org_no,
            "src_sys_no": src_sys_no,
            "channel": channel,
            "uploaded_file_path": "",
            "thread_id": thread_id,
            "request_id": request_id,
            "original_user_text": message or audit_text,
        }
    )

    try:
        await asyncio.to_thread(
            record_turn_start,
            {
                "request_id": request_id,
                "thread_id": thread_id,
                "user_id": user_id,
                "user_name": user_name,
                "channel": channel,
                "messages": [{"role": "user", "content": audit_text}],
                "original_user_text": message or audit_text,
            },
        )

        payload: dict = {"decision": decision}
        if decision == "edit":
            payload["edited_args"] = edited_args or {}
        elif decision == "reject":
            payload["message"] = message or "用户拒绝了该操作"

        interactive = InteractiveInput()
        interactive.update(interrupt_id, payload)
        v3_sessions.clear_pending_interrupt(thread_id)

        agent = await get_v3_agent()
        session = v3_sessions.new_run_session(thread_id, card=agent.card)

        # 新一轮若再出 __interaction__（reject 后模型重试），bridge 会自动
        # set 新 pending id——天然支持二次审批，无需额外代码。
        # 注：resume 也注册取消（刻意改进，v2 的 resume 不可取消）——
        # 审批通过后的长工具（modify_report 等）执行期间用户可停止。
        final_status = "success"
        failure_reason = ""
        final_values: dict = {}
        async for frame_text in stream_v3_events(
            agent=agent,
            session=session,
            inputs={"query": interactive},
            request_id=request_id,
            thread_id=thread_id,
            is_cancelled=cancel_event.is_set,
        ):
            if '"type": "cancelled"' in frame_text:
                final_status = "cancelled"
                failure_reason = "用户取消任务"
            elif '"type": "done"' in frame_text:
                final_values = _done_frame_final_values(frame_text)
            yield frame_text

        duration_ms = int((time.monotonic() - started) * 1000)
        await asyncio.to_thread(
            finish_turn, request_id, final_status, duration_ms, final_values,
            failure_reason=failure_reason,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.exception("agent_v3 resume 异常: thread=%s request=%s", thread_id, request_id)
        await asyncio.to_thread(
            finish_turn, request_id, "failed", duration_ms, failure_reason=str(exc)[:500]
        )
        yield _frame("error", {"message": str(exc)[:300]})
    finally:
        _cancelled.pop(thread_id, None)
        reset_request_context(ctx_token)


#: steer 等待旧 run 释放 thread/缓冲槽位的超时（秒）。正常取消在 0.5s
#: 轮询粒度内生效，这里留足工具收尾与帧搬运的余量。
_STEER_RELEASE_TIMEOUT_S = 15.0


def _detach_context_snapshot(agent, thread_id: str) -> dict | None:
    """把该 thread 在上下文池里的现场制成 sanitized 快照并从池中摘除。

    框架 _inner_stream 把真正的执行放在独立 task（stream_process）里，外层
    生成器被 aclose 时该 task 不会被取消——被取消的 run 常仍在后台续跑并
    继续往池内上下文追加消息。若新 run 与之共享同一上下文对象，双方交错
    追加会把历史搅成 OpenAI 协议 400（assistant.tool_calls 与 tool 结果不
    配对、user 消息插在 assistant/tool 之间）。摘除后旧 run 只污染它自己
    持有的旧对象；快照由调用方经 session state 注入新 run（create_context
    时 _load_state_from_session 用快照重建 buffer），得到干净副本。

    返回 {context_id: {"messages": [...]}} 形式的快照；池中没有该 thread
    的上下文（如进程重启后）时返回 None，调用方不得注入——历史应由
    checkpoint 恢复，注入空快照反而会覆盖它。
    """
    import copy

    engine = getattr(agent, "context_engine", None)
    sanitize = getattr(agent, "_sanitize_cancelled_turn_messages", None)
    if engine is None or sanitize is None:
        return None
    pool = getattr(engine, "_context_pool", None)
    if not isinstance(pool, dict):
        return None
    snapshot: dict = {}
    for full_id, context in list(pool.items()):
        try:
            if context.session_id() != thread_id:
                continue
            # 必须取全量（含 history 前缀）：框架 load_state → rebulid 会把恢复
            # 的消息全部标为 history（_history_messages_size = len），若此处用
            # with_history=False 只能拿到尾部，第二次插话时快照会丢掉全部
            # 真实历史（只余插话消息与 cancelled 标记），模型随之"失忆"。
            messages = context.get_messages(with_history=True)
            if messages:
                kept = sanitize(messages)
                snapshot[context.context_id()] = {"messages": copy.deepcopy(kept)}
            pool.pop(full_id, None)
        except Exception:
            logger.warning("agent_v3 上下文池隔离跳过异常项: thread=%s", thread_id,
                           exc_info=True)
    return snapshot or None


async def stream_agent_steer(
    thread_id: str,
    message: str,
    original_user_text: str = "",
    user_id: str = "",
    user_name: str = "",
    org_no: str = "",
    src_sys_no: str = "",
    channel: str = "",
) -> AsyncGenerator[str, None]:
    """任意时刻插话：打断当前 run，以插话为新 user 消息带 checkpoint 续跑。

    语义与前端体验对齐"任务跑到一半插句话"：旧 run 作废（turn 记 cancelled），
    新 run 复用同一 thread_id —— checkpoint 恢复历史会话与业务 state
    （analysis_queue/activity_list/report_context），模型带着已完成结果+插话
    重新规划，不重跑已完成的工作。

    两道前置校验：
    - 有待决审批时拒绝 —— 新 run 会清掉 /resume 正要恢复的现场（sessions.py 注释）；
    - 无活跃 run 时拒绝 —— 插话无对象，前端应直接走 /run。
    """
    if v3_sessions.get_pending_interrupt(thread_id) is not None:
        yield _frame("error", {"message": "该会话正在等待审批，请先处理审批卡片"})
        return
    if not request_cancel(thread_id):
        yield _frame("error", {"message": "该会话没有正在运行的任务，请直接发送消息"})
        return

    # 等旧 run 的 stream_agent_run 走完 finally、释放 _cancelled 注册表
    # （stream_agent_run 开头靠该注册表保证同 thread 单活跃 run）。
    # 只需盯注册表：旧 run 的 cancelled 帧发布到它自己的旧缓冲对象（槽位已被
    # steer 的 replace 接管，两者互不影响），注册表释放即旧 run 彻底收尾。
    deadline = time.monotonic() + _STEER_RELEASE_TIMEOUT_S
    while thread_id in _cancelled:
        if time.monotonic() > deadline:
            logger.warning("agent_v3 steer 等待旧 run 释放超时: thread=%s", thread_id)
            yield _frame("error", {"message": "打断当前任务超时，请稍后重试"})
            return
        await asyncio.sleep(0.05)

    async for frame_text in stream_agent_run(
        thread_id=thread_id,
        message=message,
        original_user_text=original_user_text or message,
        user_id=user_id,
        user_name=user_name,
        org_no=org_no,
        src_sys_no=src_sys_no,
        channel=channel,
    ):
        yield frame_text
