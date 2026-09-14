"""审批确认话术生成：中断时用一次轻量 LLM 调用把工具调用转述为用户可读文案。

设计约束：
- 话术只是审批卡片的"副标题"：卡片正文（活动列表/参数）仍由确定性渲染，
  避免模型编造的活动名成为唯一信息源；
- 任何失败/超时返回空串，由调用方回退到模板文案，弹窗不被 LLM 阻塞。
"""
from __future__ import annotations

import logging

from src.llm import get_model

logger = logging.getLogger("activity-analysis.agent")

#: 话术最大长度（超出视为模型失控，弃用回退）
_MAX_WORDING_CHARS = 120

_PROMPT = """你正在为银行营销活动分析助手的操作确认弹窗撰写一句确认说明。

用户即将确认的操作：
- 操作类型：{tool_display}
- 操作参数：{args_summary}
- 涉及活动：{activities}
{overwrite_line}
要求：
- 用一两句话向用户说明"将要做什么、依据是什么、有什么后果"；
- 60 字以内，口语化，无 markdown、无表情符号；
- 不要出现参数字段名（如 activity_ids、data_source）；
- 只输出说明文字本身，不要引号。
"""


async def generate_approval_wording(
    tool_display: str,
    args_summary: dict | None = None,
    activity_names: list[str] | None = None,
    overwrite: bool = False,
) -> str:
    """生成审批确认话术；失败/异常/输出不合格时返回空串（调用方回退模板）。"""
    args_text = "；".join(f"{k}={v}" for k, v in (args_summary or {}).items()) or "无"
    activities_text = "、".join(activity_names or []) or "（不涉及具体活动）"
    overwrite_line = "- 重要：用户当前已有一份报告，本次操作会覆盖它。\n" if overwrite else ""
    prompt = _PROMPT.format(
        tool_display=tool_display,
        args_summary=args_text,
        activities=activities_text,
        overwrite_line=overwrite_line,
    )
    try:
        model = get_model("approval_wording")
        response = await model.invoke(prompt)
    except Exception as exc:
        logger.info("审批话术生成失败，回退模板文案: %s", exc)
        return ""
    text = str(getattr(response, "content", "") or "").strip().strip('"\'“”')
    text = " ".join(text.split())
    if not text or len(text) > _MAX_WORDING_CHARS:
        logger.info("审批话术不合格（%d 字），回退模板文案", len(text))
        return ""
    return text
