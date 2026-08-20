"""agent_v3 工具层：openjiuwen @tool 壳 + impl 层直调。

壳内统一模式：组装 ToolContext（会话状态快照 + ToolRequestContext + 流写入闭包）
→ 调 impl 业务函数（agent_v3/tools/impl/，无框架依赖）→ ToolOutcome.state_updates
写回 agent-core 会话全局状态；impl 返回 str 时直传。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from openjiuwen.core.foundation.tool import tool
from openjiuwen.core.session import get_current_session

from src.agent_v3.request_context import get_request_context
from src.agent_v3.tools.impl import ToolContext, ToolOutcome
from src.agent_v3.tools.impl import activity_query as impl_activity_query
from src.agent_v3.tools.impl import analysis_queue as impl_analysis_queue
from src.agent_v3.tools.impl import data_parse as impl_data_parse
from src.agent_v3.tools.impl import report_export as impl_report_export
from src.agent_v3.tools.impl import report_gen as impl_report_gen
from src.agent_v3.tools.impl import report_modify as impl_report_modify
from src.agent_v3.tools.impl import skill as impl_skill
from src.agent_v3.tools.impl import template as impl_template
from src.agent_v3.tools.impl.context import ToolRequestContext

logger = logging.getLogger("njbank.agent")

#: impl 经 ToolContext.state 可能读取的 state 键全集（会话状态部分）
_SESSION_STATE_KEYS = (
    "analysis_queue",
    "activity_list",
    "activity_list_request_id",
    "report_context",
    "html_report",
    "uploaded_activity_dataset",
    "data_summary",
    "formatted_output_path",
)


def _state_snapshot(session) -> dict:
    snapshot: dict[str, Any] = {}
    for key in _SESSION_STATE_KEYS:
        value = session.get_state(key)
        if value is not None:
            snapshot[key] = value
    return snapshot


def _make_stream_writer(session, loop):
    """组装 ToolContext.write_stream：把 impl 的同步进度事件桥到会话 custom 流。

    impl 的报告管线在 asyncio.to_thread 工作线程里调 writer（同步函数）；
    闭包经 run_coroutine_threadsafe 把进度帧写回主事件循环的会话流。
    session 为 None 时返回 no-op。
    """
    if session is None:
        return lambda _event: None

    def write(event) -> None:
        asyncio.run_coroutine_threadsafe(
            session.write_custom_stream(dict(event)), loop)

    return write


async def _run(impl_fn, args: dict) -> str:
    """组装 ToolContext → 调 impl → ToolOutcome.state_updates 写会话。"""
    try:
        session = get_current_session()
    except Exception:
        session = None
    state = _state_snapshot(session) if session is not None else {}
    req = ToolRequestContext(**{k: v for k, v in get_request_context().items()
                                if k in ToolRequestContext.model_fields})
    ctx = ToolContext(state=state, request=req,
                      write_stream=_make_stream_writer(session, asyncio.get_running_loop()))
    result = await impl_fn(ctx, **args)
    if isinstance(result, ToolOutcome):
        if result.state_updates:
            if session is not None:
                session.update_state(result.state_updates)
            else:
                logger.warning("agent_v3 工具 %s 的状态更新被丢弃（无会话）: keys=%s",
                               getattr(impl_fn, "__name__", "?"), list(result.state_updates))
        return result.content
    return result


@tool
async def search_activities(keyword: str = "", activity_type: str = "", channel: str = "",
                            start_date: str = "", end_date: str = "", limit: int = 20) -> str:
    """按关键词/渠道/日期等条件查询银行营销活动，返回活动列表。参数：keyword 活动查询文本；活动名称、活动编号、ID 或纯数字均填写此字段，底层统一使用 actName 查询；activity_type 活动类型（线上/线下），不确定留空；channel 渠道，如'短信'、'外呼'，不确定留空；start_date 活动开始日期下限，格式 YYYY-MM-DD 或 YYYYMMDD；end_date 活动结束日期上限，格式 YYYY-MM-DD 或 YYYYMMDD；limit 返回给用户看的最大条数，默认 20。"""
    return await _run(impl_activity_query.search_activities,
                      dict(keyword=keyword, activity_type=activity_type, channel=channel,
                           start_date=start_date, end_date=end_date, limit=limit))


@tool
async def get_activity_detail(activity_id: str) -> str:
    """查看单个活动的详细信息。优先使用最近查询结果，未命中则回源查询。参数：activity_id 活动编号（act_no / activity_id）。"""
    return await _run(impl_activity_query.get_activity_detail,
                      dict(activity_id=activity_id))


@tool
async def get_available_templates(template_type: str = "", keyword: str = "") -> str:
    """查询可用的分析报告模板（含模板包含的分析技能列表）。参数：template_type 模板类型（线上/线下/通用），不确定留空；keyword 模板名称关键词，如'外呼'、'短信'。"""
    return await _run(impl_template.get_available_templates,
                      dict(template_type=template_type, keyword=keyword))


@tool
async def get_available_skills(category: str = "", keyword: str = "") -> str:
    """查询系统中所有可用的分析 skill（分析组件），不限于已加入分析模板的 skill。参数：category skill 分类名称（如'活动分析'），不确定留空；keyword skill 名称关键词，如'转化'、'趋势'。"""
    return await _run(impl_skill.get_available_skills,
                      dict(category=category, keyword=keyword))


@tool
async def parse_uploaded_data(confirm: bool = True) -> str:
    """解析用户当前上传的活动数据文件，生成结构化数据集和活动列表。参数：confirm 确认解析当前上传文件（模型无需修改）。"""
    return await _run(impl_data_parse.parse_uploaded_data, dict(confirm=confirm))


@tool
async def add_to_analysis_queue(activity_ids: list[str], perspective: str = "",
                                metrics: list[str] | None = None,
                                dimensions: list[str] | None = None) -> str:
    """仅当用户明确要求加入/添加/放入分析队列时，将已核实活动加入待分析队列。用户只是选择活动并要求效果比较、优劣分析或下一步建议时不要调用本工具，应直接使用 generate_report 分析已选活动。参数：activity_ids 要加入分析队列的活动编号列表；perspective 分析视角，可选；metrics 分析指标列表，可选；dimensions 分析维度列表，可选。"""
    return await _run(impl_analysis_queue.add_to_analysis_queue,
                      dict(activity_ids=activity_ids, perspective=perspective,
                           metrics=metrics, dimensions=dimensions))


@tool
async def remove_from_analysis_queue(activity_ids: list[str]) -> str:
    """将指定活动移出当前会话的待分析队列。参数：activity_ids 要从分析队列移除的活动编号列表。"""
    return await _run(impl_analysis_queue.remove_from_analysis_queue,
                      dict(activity_ids=activity_ids))


@tool
async def update_analysis_config(activity_id: str, perspective: str = "",
                                 metrics: list[str] | None = None,
                                 dimensions: list[str] | None = None) -> str:
    """调整分析队列中某个活动的分析配置（指标/维度/视角）。参数：activity_id 要调整配置的活动编号；perspective 分析视角，可选；metrics 分析指标列表，可选；省略时保持原值；dimensions 分析维度列表，可选；省略时保持原值。"""
    return await _run(impl_analysis_queue.update_analysis_config,
                      dict(activity_id=activity_id, perspective=perspective,
                           metrics=metrics, dimensions=dimensions))


@tool
async def get_report_content(summary_length: int = 2000) -> str:
    """获取当前已生成报告的 HTML 文本摘要与版本信息，供 modify_report 前的审视使用。参数：summary_length 返回文本摘要的最大字符数。"""
    return await _run(impl_report_modify.get_report_content,
                      dict(summary_length=summary_length))


@tool
async def generate_report(activity_ids: list[str] | None = None,
                          data_source: Literal["activity_query", "uploaded", "analysis_queue"] = "analysis_queue",
                          metrics: list[str] | None = None,
                          dimensions: list[str] | None = None,
                          perspective: str | None = None,
                          chart_style: str | None = None,
                          report_theme: str | None = None,
                          analysis_focus: str = "",
                          confirm_mixed: bool = False) -> str:
    """为指定活动生成 HTML 分析报告。可指定分析指标、维度、视角等参数；更换指标/维度/视角重新分析时，用新参数再次调用本工具。参数：activity_ids 要分析的活动编号列表；为 null 时取分析队列中的活动；data_source 数据来源：analysis_queue=分析队列（默认），activity_query=显式指定活动，uploaded=已解析的上传文件；metrics 分析指标，如 ['conversion_rate','roi']；dimensions 分析维度，如 ['region','channel']；perspective 分析视角：outbound_call_analysis（外呼）/ sms_analysis（短信）/ comprehensive_operations（综合运营）；chart_style 图表类型偏好，如 'bar'、'line'、'pie'；report_theme 报告主题色偏好；analysis_focus 自由文本补充分析要求；confirm_mixed 外呼视角下混合活动确认：首次调用返回 need_confirm 后，用户确认继续生成时置 true 重新调用。"""
    return await _run(impl_report_gen.generate_report,
                      dict(activity_ids=activity_ids, data_source=data_source,
                           metrics=metrics, dimensions=dimensions, perspective=perspective,
                           chart_style=chart_style, report_theme=report_theme,
                           analysis_focus=analysis_focus, confirm_mixed=confirm_mixed))


@tool
async def modify_report(content_changes: list[str] | None = None,
                        chart_replacements: list[dict] | None = None,
                        style_changes: list[str] | None = None,
                        free_instruction: str = "") -> str:
    """基于当前报告 HTML 和用户结构化修改指令，生成修改后的新版本报告。参数：content_changes 内容修改要求列表，如 ['增加客群规模章节', '把结论写得更简洁']；chart_replacements 图表替换要求，如 [{'chart_id':'chart1','to_chart_type':'pie'}]；style_changes 样式修改要求列表，如 ['使用深色主题', '标题居中']；free_instruction 自由文本修改要求。"""
    return await _run(impl_report_modify.modify_report,
                      dict(content_changes=content_changes,
                           chart_replacements=chart_replacements,
                           style_changes=style_changes,
                           free_instruction=free_instruction))


@tool
async def export_report(format: str = "html", output_filename: str = "") -> str:
    """将当前报告导出为 HTML 文件。参数：format 导出格式：html；output_filename 可选文件名（不含扩展名），为空时使用 report-{report_id}。"""
    return await _run(impl_report_export.export_report,
                      dict(format=format, output_filename=output_filename))


@tool
async def write_todos(todos: list[str]) -> str:
    """将当前任务的待办清单写入会话（规划辅助）。参数：todos 待办事项文本列表。"""
    session = get_current_session()
    session.update_state({"todos": list(todos)})
    return f"已记录 {len(todos)} 条待办"


# 长耗时工具的超时豁免：openjiuwen 默认每次工具调用 300s 超时
# （ability_manager.DEFAULT_TOOL_CALL_TIMEOUT），超时后工具被取消但 to_thread
# 里的管线继续跑——模型收到超时错误而报告其实稍后才写完（联调实测 361s）。
# 经 ToolCard.properties["resilience"]["timeout_s"] 放宽（硬上限 3600s）。
_LONG_RUNNING_TOOL_TIMEOUT_S = 1200.0
for _t in (generate_report, modify_report):
    _t.card.properties.setdefault("resilience", {})["timeout_s"] = _LONG_RUNNING_TOOL_TIMEOUT_S


ALL_V3_TOOLS = [
    search_activities,
    get_activity_detail,
    get_available_templates,
    get_available_skills,
    parse_uploaded_data,
    add_to_analysis_queue,
    remove_from_analysis_queue,
    update_analysis_config,
    get_report_content,
    generate_report,
    modify_report,
    export_report,
    write_todos,
]

# SSE node_update 帧的中文展示名（与旧系统 NODE_DISPLAY_NAME 风格一致；
# 从 agent_v2/tools/__init__.py 逐字平移）
TOOL_DISPLAY_NAMES = {
    "search_activities": "查询活动",
    "get_activity_detail": "查看活动详情",
    "add_to_analysis_queue": "加入分析队列",
    "remove_from_analysis_queue": "移出分析队列",
    "update_analysis_config": "调整分析配置",
    "parse_uploaded_data": "解析上传数据",
    "get_available_templates": "获取分析模板",
    "get_available_skills": "获取分析组件",
    "generate_report": "生成分析报告",
    "modify_report": "修改报告",
    "export_report": "导出报告",
    "get_report_content": "查看当前报告",
}

# 写操作工具（接 ApprovalEditRail 人机确认；从 agent_v2/tools/__init__.py 逐字平移）
WRITE_TOOLS = {
    "add_to_analysis_queue",
    "remove_from_analysis_queue",
    "update_analysis_config",
    "modify_report",
}
