"""thread_id → agent-core Session 注册表与待决中断登记。

P2 起状态连续性由持久化 checkpointer 保证（state/persistence.py，
SQLite data/v3_checkpoints.db，框架自动 pre_run recover / post_run save）；
本注册表只保存进程内活跃实例（done 帧读业务状态用）与待决中断
（pending_interrupt 仍为进程内——审批中断的跨重启恢复不在 P2 范围）。
"""
from __future__ import annotations

import logging
import threading

from openjiuwen.core.session.agent import create_agent_session

logger = logging.getLogger("njbank.agent")

_sessions: dict[str, object] = {}
_pending_interrupts: dict[str, str] = {}
_lock = threading.Lock()

#: done 帧需要从会话状态读取的业务键及其默认值
_BUSINESS_STATE_DEFAULTS = {
    "html_report": "",
    "analysis_queue": [],
    "report_context": {},
    "activity_list": [],
    "formatted_output_path": "",
}


def new_run_session(thread_id: str, card=None):
    """为一次 run 创建新的 AgentSession（框架设计：会话实例一次性，状态连续性
    由 checkpointer 按 session_id 保证——Runner 自己的路径也是每轮新建实例）。

    不能复用实例：post_run 默认 close_stream_on_post_run=True，复用会在第二轮
    报 "StreamQueue is already closed"（联调实测）。card 必须传：缺 card 时
    pre_run 在 checkpointer 取 agent_id() 报 AttributeError（'NoneType'.id）。

    最新实例登记在注册表，供 read_business_state 在轮次结束后读业务状态
    （post_run 已 commit，对象内内存状态仍有效）。
    """
    if card is None:
        raise ValueError("创建会话必须提供 agent card")
    session = create_agent_session(session_id=thread_id, card=card)
    with _lock:
        _sessions[thread_id] = session
    return session


def set_pending_interrupt(thread_id: str, interrupt_id: str) -> None:
    with _lock:
        _pending_interrupts[thread_id] = interrupt_id


def get_pending_interrupt(thread_id: str) -> str | None:
    with _lock:
        return _pending_interrupts.get(thread_id)


def clear_pending_interrupt(thread_id: str) -> None:
    with _lock:
        _pending_interrupts.pop(thread_id, None)


async def prepare_fresh_run_session(session, inputs=None) -> tuple[bool, int]:
    """新一轮 run 前准备已 recover 的会话：作废残留中断 + 修补悬空 tool_calls。

    返回 (是否作废了残留中断, 修补的悬空 tool_call 条数)。

    提前 pre_run recover（幂等，Runner 内会跳过）。仅用于"进程内无待决审批"
    的新一轮 run；进程内待决审批（pending_interrupts 有登记）时绝不可调用——
    那会清掉 /resume 正要恢复的现场。

    两件事都以 checkpoint 恢复后的 session state 为准：
    1. 作废残留中断：审批挂起中进程重启后，`__react_agent_interruption__`
       仍在 state 里；不清则框架主循环走中断恢复分支，把新消息吞进
       INTERACTIVE_INPUT、不进对话上下文（用户提问丢失）。按 P2 设计预期
       此时"审批作废、新消息正常处理"。
    2. 修补悬空 tool_calls：中断/异常落库的上下文可能留有"带 tool_calls
       的 assistant 消息但无 tool 结果"，直接发新消息会被 OpenAI 协议
       拒绝（400）。与是否残留中断无关，每次 fresh run 都检查。
    """
    from openjiuwen.core.single_agent.interrupt.state import INTERRUPTION_KEY

    await session.pre_run(inputs=inputs)
    discarded = False
    if session.get_state(INTERRUPTION_KEY) is not None:
        # 与框架 _clear_interruption_state 相同的清除方式
        session.update_state({INTERRUPTION_KEY: None})
        discarded = True
    repaired = repair_dangling_tool_calls(session)
    return discarded, repaired


def repair_dangling_tool_calls(session) -> int:
    """为上下文中悬空的 assistant tool_calls 补合成 tool 响应，返回修补条数。

    审批中断时上下文最后一条是带 tool_calls 的 assistant 消息、没有对应
    tool 结果；作废中断后直接发新消息会被 OpenAI 协议拒绝（400：
    tool_calls must be followed by tool messages）。为每个缺失的
    tool_call_id 在其归属 assistant 消息后补一条"已作废"的 tool 消息，
    保持上下文协议完整，同时让模型知晓该操作未执行。
    """
    from openjiuwen.core.foundation.llm import ToolMessage

    contexts = session.get_state("context")
    if not isinstance(contexts, dict):
        return 0
    repaired = 0
    for ctx_state in contexts.values():
        messages = ctx_state.get("messages") if isinstance(ctx_state, dict) else None
        if not isinstance(messages, list) or not messages:
            continue
        answered = {
            getattr(m, "tool_call_id", None)
            for m in messages
            if getattr(m, "tool_call_id", None)
        }
        new_messages = []
        for msg in messages:
            new_messages.append(msg)
            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id and tc_id not in answered:
                    new_messages.append(ToolMessage(
                        tool_call_id=tc_id,
                        content="该操作未执行（审批在服务重启前未完成，已作废）。",
                    ))
                    repaired += 1
        if len(new_messages) != len(messages):
            ctx_state["messages"] = new_messages
    if repaired:
        session.update_state({"context": contexts})
    return repaired


def read_business_state(thread_id: str) -> dict:
    with _lock:
        session = _sessions.get(thread_id)
    state = {key: (list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value)
             for key, value in _BUSINESS_STATE_DEFAULTS.items()}
    if session is None:
        return state
    for key, default in _BUSINESS_STATE_DEFAULTS.items():
        value = session.get_state(key)
        state[key] = value if value is not None else default
    return state


def reset_sessions() -> None:
    with _lock:
        _sessions.clear()
        _pending_interrupts.clear()
