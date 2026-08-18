"""工具实现层共享辅助（从 agent_v2/tools/_common.py 平移，去旧框架依赖）。

约定：
- 失败一律返回 "ERROR: <原因>" 文本（不抛异常），由 System Prompt 约束模型如实转述；
- 需要写图状态的工具通过 ToolOutcome.state_updates 返回（替代 v2 的 tool_command/Command）；
- 请求级参数（user_id/org_no/...）只从 ToolContext.request 或
  request_context.ContextVar 读取，禁止 LLM 生成。
"""
from __future__ import annotations

import json
from typing import Any

from src.domain.activity_status import display_activity_status
from src.utils.token_budget import ModelContextLengthExceeded, is_provider_context_limit_error


# ── 活动字段紧凑化（映射拷贝自 api/routers/conversations.py，保持两边一致）──

def activity_key(activity: dict) -> str:
    return str(
        activity.get("activity_id")
        or activity.get("act_no")
        or activity.get("actNo")
        or activity.get("活动编号")
        or ""
    )


def activity_name(activity: dict) -> str:
    return str(
        activity.get("name")
        or activity.get("activity_name")
        or activity.get("act_name")
        or activity.get("actName")
        or activity.get("活动名称")
        or activity_key(activity)
        or "未命名活动"
    )


def compact_activity(activity: dict) -> dict:
    raw_status = activity.get("status") or activity.get("actStatusCd") or activity.get("活动状态") or ""
    return {
        "activity_id": activity_key(activity),
        "name": activity_name(activity),
        "channel": activity.get("channel") or activity.get("渠道") or "",
        "activity_type": activity.get("activity_type") or activity.get("actTypeCd") or activity.get("活动类型") or "",
        "status": display_activity_status(raw_status),
        "status_code": str(raw_status).strip(),
        "start_date": activity.get("start_date") or activity.get("actStartDt") or activity.get("活动开始日期") or "",
        "end_date": activity.get("end_date") or activity.get("actEndDt") or activity.get("活动结束日期") or "",
        "goal": activity.get("goal") or activity.get("target") or activity.get("活动运营目标") or "",
        "content": activity.get("content") or activity.get("actDesc") or activity.get("活动内容") or "",
    }


# ── 返回协议 ──

def ok_content(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def error_content(message: str) -> str:
    return f"ERROR: {message}"


def summarize(text: str, limit: int = 200) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


# ── 异常识别 ──

_TIMEOUT_TYPE_MARKERS = frozenset({"timeout", "timedout", "deadline", "readtimeout", "connecttimeout"})
_TIMEOUT_MESSAGE_MARKERS = frozenset({"timeout", "timed out", "time out", "请求超时", "连接超时", "读取超时", "deadline exceeded"})


def _iter_causes(exc: BaseException | None):
    """沿 __cause__/__context__ 链遍历异常（带环保护）。"""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)


def is_timeout_exception(exc: BaseException | None) -> bool:
    """判断异常是否由 LLM/网络访问超时触发。

    兼容多提供商异常类型（openai/anthropic/httpx/google 等）、被包装后
    只能通过消息判断的场景，以及框架包装异常（openjiuwen 会把提供商
    原始异常放进 FrameworkError.__cause__，需沿因果链向下找）。
    """
    if exc is None:
        return False
    for cause in _iter_causes(exc):
        exc_type = type(cause)
        type_name = f"{exc_type.__module__}.{exc_type.__name__}".lower()
        if any(marker in type_name for marker in _TIMEOUT_TYPE_MARKERS):
            return True
        if isinstance(cause, TimeoutError):
            return True
        message = str(cause).lower()
        if any(marker in message for marker in _TIMEOUT_MESSAGE_MARKERS):
            return True
    return False


def is_context_length_exception(exc: BaseException | None) -> bool:
    """识别模型或兼容网关返回的上下文/Token 超限异常。"""
    return isinstance(exc, ModelContextLengthExceeded) or is_provider_context_limit_error(exc)
