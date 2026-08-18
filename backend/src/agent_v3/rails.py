"""agent_v3 自定义 Rail：审批三决策 / 工具调用上限 / 工具进度流帧。

工具结果摘要/参数摘要/报告上下文剥字段复用 events/_frames 的私有函数
（从 v2 sse_bridge 平移，截断与剥字段语义与 SSE 帧完全一致，避免双份漂移）。
"""
from __future__ import annotations

import json
import logging
from typing import Iterable, Optional

from openjiuwen.core.foundation.llm import ToolMessage
from openjiuwen.core.single_agent.interrupt.response import InterruptRequest
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext, AgentRail
from openjiuwen.core.foundation.llm.schema.tool_call import ToolCall
from openjiuwen.harness.rails.interrupt.interrupt_base import (
    BaseInterruptRail, InterruptDecision,
)

from src.agent_v3.events._frames import (
    _args_summary, _compact_report_context, _summarize_content,
)
from src.agent_v3.tools import TOOL_DISPLAY_NAMES

logger = logging.getLogger("njbank.agent")


def _normalize_tool_args(tool_args) -> dict:
    """openjiuwen 的 tool_args 是 JSON 字符串（ToolCall.arguments），
    归一为 dict 供 ``_args_summary``（只认 dict）使用；解析失败给 {}。"""
    if isinstance(tool_args, dict):
        return tool_args
    if isinstance(tool_args, str) and tool_args.strip():
        try:
            parsed = json.loads(tool_args)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}

#: resume payload 的 JSON Schema（随中断帧透传给前端/调用方，自描述用）
APPROVAL_PAYLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["approve", "edit", "reject"]},
        "edited_args": {"type": "object"},
        "message": {"type": "string"},
    },
    "required": ["decision"],
}


class ApprovalEditRail(BaseInterruptRail):
    """写工具审批：approve / edit（改写参数）/ reject（feedback 回传模型）。

    对标 v2 interrupt_on 的 allowed_decisions=["approve", "edit", "reject"]。
    """

    def __init__(self, tool_names: Optional[Iterable[str]] = None,
                 message: str = "请确认是否执行该操作"):
        super().__init__(tool_names=tool_names)
        self._message = message

    async def resolve_interrupt(
            self,
            ctx: AgentCallbackContext,
            tool_call: Optional[ToolCall],
            user_input,
            auto_confirm_config: Optional[dict] = None,
    ) -> InterruptDecision:
        if not isinstance(user_input, dict):
            return self.interrupt(InterruptRequest(
                message=self._approval_message(tool_call),
                payload_schema=APPROVAL_PAYLOAD_SCHEMA,
            ))
        decision = user_input.get("decision")
        if decision == "approve":
            return self.approve()
        if decision == "edit":
            edited_args = user_input.get("edited_args") or {}
            return self.approve(new_args=json.dumps(edited_args, ensure_ascii=False))
        if decision == "reject":
            feedback = (user_input.get("message") or "用户拒绝了该操作").strip()
            return self.reject(tool_result=(
                f"用户拒绝了本次操作。用户反馈：{feedback}。"
                "请尊重用户决定，不要再调用该工具，直接用文字回复用户。"
            ))
        return self.interrupt(InterruptRequest(
            message=self._approval_message(tool_call),
            payload_schema=APPROVAL_PAYLOAD_SCHEMA,
        ))

    def _approval_message(self, tool_call: Optional[ToolCall]) -> str:
        """按工具定制审批文案（对齐 v2 interrupt_on 行为）；无工具名时回退泛化文案。"""
        tool_name = getattr(tool_call, "name", "") if tool_call else ""
        if not tool_name:
            return self._message
        return f"请确认是否执行「{TOOL_DISPLAY_NAMES.get(tool_name, tool_name)}」"


class ToolCallLimitRail(AgentRail):
    """每轮（一次 invoke）工具调用上限，对标 v2 ToolCallLimitMiddleware(run_limit=8)。

    计数按会话隔离：agent 是进程级单例，若用 Rail 实例上的单一计数器，
    并发会话会互相吃掉工具额度（v2 计数在 per-run 图状态里天然隔离）。
    故计数器为 ``{session_id: count}``，before_invoke 只重置当前会话。
    """

    def __init__(self, max_calls: int = 8):
        self._max_calls = max_calls
        self._counts: dict[str, int] = {}

    @staticmethod
    def _session_key(ctx) -> Optional[str]:
        session = getattr(ctx, "session", None)
        if session is not None:
            session_id = session.get_session_id()
            if session_id:
                return session_id
        return getattr(ctx.inputs, "conversation_id", None)

    async def before_invoke(self, ctx) -> None:
        key = self._session_key(ctx)
        if key is None:
            # 拿不到任何会话标识时兜底清空，避免脏计数泄漏到无法归类的调用
            self._counts.clear()
        else:
            self._counts[key] = 0

    async def before_tool_call(self, ctx) -> None:
        key = self._session_key(ctx)
        if key is None:
            # 无会话标识的调用不纳入限额（不污染其他会话计数）
            return
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        if count <= self._max_calls:
            return
        tool_call = ctx.inputs.tool_call
        tool_call_id = getattr(tool_call, "id", "") if tool_call else ""
        ctx.extra["_skip_tool"] = True
        ctx.inputs.tool_result = (
            f"本轮工具调用次数已达上限（{self._max_calls} 次），本次调用已跳过。"
            "不要再调用该工具，请基于已获得的信息直接回复用户。"
        )
        ctx.inputs.tool_msg = ToolMessage(content=ctx.inputs.tool_result,
                                          tool_call_id=tool_call_id)


class ToolProgressRail(AgentRail):
    """工具进度与业务状态透传：以 custom 流帧发出，由 v3 sse_bridge 转 SSE。

    agent-core 流式无工具开始/结束帧（react_agent 源码确认），进度帧只能由 Rail 自发。
    """

    def __init__(self,
                 suppressed_tools=frozenset({"generate_report"}),
                 safe_state_keys=("analysis_queue", "activity_list", "report_context",
                                  "report_html_guard_result", "formatted_output_path")):
        self._suppressed = suppressed_tools
        self._safe_state_keys = safe_state_keys

    async def before_tool_call(self, ctx) -> None:
        if ctx.inputs.tool_name in self._suppressed or ctx.session is None:
            return
        await ctx.session.write_custom_stream({
            "njbank": "tool_progress",
            "tool": ctx.inputs.tool_name,
            "status": "running",
            "args_summary": _args_summary(_normalize_tool_args(ctx.inputs.tool_args)),
        })

    async def after_tool_call(self, ctx) -> None:
        if ctx.session is None:
            return
        if ctx.inputs.tool_name not in self._suppressed:
            await ctx.session.write_custom_stream({
                "njbank": "tool_progress",
                "tool": ctx.inputs.tool_name,
                "status": "done",
                "summary": _summarize_content(ctx.inputs.tool_result),
            })
        data = {}
        for key in self._safe_state_keys:
            value = ctx.session.get_state(key)
            if value:
                data[key] = value
        if "report_context" in data:
            data["report_context"] = _compact_report_context(data["report_context"])
        if data:
            await ctx.session.write_custom_stream({"njbank": "state_update", "data": data})
