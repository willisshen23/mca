"""请求级上下文的 ContextVar 兜底通道（从 agent_v2/state/request_context.py 平移）。

主通道是壳层组装的 ToolContext.request（agent_v3/tools/impl/context.py）。
本模块是兜底通道：某些代码路径拿不到 ToolContext（例如在 asyncio.to_thread
线程中执行的报告管线 seed 构建），可从这里的 ContextVar 读取。

runtime 在每次请求开始时 set，结束时 reset。
"""
from __future__ import annotations

import contextvars

_current: contextvars.ContextVar[dict] = contextvars.ContextVar(
    "agent_v3_request_context",
    default={},
)


def set_request_context(ctx: dict) -> contextvars.Token:
    return _current.set(ctx)


def reset_request_context(token: contextvars.Token) -> None:
    _current.reset(token)


def get_request_context() -> dict:
    """返回当前请求上下文字典（可能为空 dict）。"""
    return _current.get()
