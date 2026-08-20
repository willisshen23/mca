"""agent_v3 工具实现层契约：ToolContext 入参 / ToolOutcome 返回。

impl 模块无任何框架依赖（无旧 LLM 框架/openjiuwen import），
壳层（agent_v3/tools/__init__.py）负责组装 ToolContext 并落 ToolOutcome。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.agent_v3.tools.impl.context import ToolRequestContext


def _noop_stream(_event: dict) -> None:
    return None


@dataclass
class ToolContext:
    state: dict
    request: ToolRequestContext
    tool_call_id: str = ""
    write_stream: Callable[[dict], None] = _noop_stream


@dataclass
class ToolOutcome:
    content: str
    state_updates: dict = field(default_factory=dict)
    # 写入会话前需按 key 做并集合并的 state 键（默认整体替换）。
    # 用于并行工具调用竞态：impl 读到的 state 快照可能早于其他调用的写入，
    # 合并必须推迟到壳层写入时（读-写之间无 await，事件循环内原子）执行。
    merge_keys: tuple = ()
