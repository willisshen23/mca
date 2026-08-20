"""工具请求上下文（从 agent_v2 AgentV2Context 平移，并入 turn 级两键）。

user_id/org_no/channel/file_path 等敏感参数只走此通道（及
request_context.ContextVar 兜底），绝不由 LLM 从对话中生成。
"""
from __future__ import annotations

from pydantic import BaseModel


class ToolRequestContext(BaseModel):
    user_id: str = ""
    user_name: str = ""
    org_no: str = ""
    src_sys_no: str = ""
    channel: str = ""
    uploaded_file_path: str = ""
    thread_id: str = ""
    request_id: str = ""
    original_user_text: str = ""
    # 报告页「组件编排」步骤预选的分析组件（[{name, cat, desc, tpl}]）；
    # 非空时报告管线跳过活动模板匹配，直接按此框架编排报告。
    report_components: list[dict] = []
