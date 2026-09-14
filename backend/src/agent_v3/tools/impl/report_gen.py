"""报告生成工具 impl：generate_report（从 agent_v2/tools/report_gen.py 平移，去框架依赖）。

内部编排 = 原样复用旧报告管线的 9 个 capability 节点函数
（template_list_fetch → template_matching → component_value_fetch →
component_value_cleanup → activity_template_matching →
marketing_report_synthesis → report_html_guard 重试循环），
行为差异全部收敛在 build_report_seed 构建的初始 state 上。

节点失败约定：返回 {"next_agent": "finalize", "final_response": "<原因>"}
→ 本模块以 PipelineAbort 捕获并转换为 "ERROR: <原因>" 工具结果。

与 v2 的差异（P3 去旧框架依赖）：
- writer 由 ToolContext.write_stream 显式注入（替代旧图框架的 get_stream_writer）；
- seed["messages"] 用纯 dict 消息（{"role": "user", "content": ...}）替代旧框架消息对象；
- GenerateReportArgs 由 pydantic 模型降级为 dataclass（Literal 仅作注解文档，
  入参校验由壳层工具 schema 负责）；
- 成功路径返回 ToolOutcome（state_updates 替代 tool_command/Command）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import uuid4

from src.report_pipeline.capabilities.activity_template_matching import activity_template_matching_node
from src.report_pipeline.capabilities.branch_drilldown import branch_drilldown_node
from src.report_pipeline.capabilities.component_value_cleanup import component_value_cleanup_node
from src.report_pipeline.capabilities.component_value_fetch import component_value_fetch_node
from src.report_pipeline.capabilities.marketing_report_synthesis import marketing_report_synthesis_node
from src.report_pipeline.capabilities.outbound_activity_data_fetch import outbound_activity_data_fetch_node
from src.report_pipeline.capabilities.report_html_guard import (
    REPORT_HTML_GUARD_FAILURE_MESSAGE,
    validate_report_html,
)
from src.report_pipeline.capabilities.selected_activity_router import selected_activity_router_node
from src.report_pipeline.capabilities.template_list_fetch import template_list_fetch_node
from src.report_pipeline.capabilities.template_matching import template_matching_node
from src.report_pipeline.capabilities.uploaded_component_value_extract import (
    uploaded_component_value_extract_node,
)
from src.report_pipeline.defaults import RUNTIME_STATE_DEFAULTS
from src.report_pipeline.period import compute_analysis_period
from src.domain.report.template_skill import build_dependent_components_from_skills
from src.agent_v3.prompts.perspectives import get_perspective, perspective_keys_text
from src.agent_v3.tools.impl import ToolContext, ToolOutcome
from src.agent_v3.tools.impl.common import (
    activity_key,
    activity_name,
    error_content,
    is_context_length_exception,
    is_timeout_exception,
    ok_content,
    summarize,
)
from src.config import get_settings
from src.services.agent_run_history_service import save_report_file
from src.services.marketing_api_service import fetch_outbound_activity_data
from src.utils.token_budget import MODEL_BUSY_MESSAGE

logger = logging.getLogger("activity-analysis.agent")


@dataclass
class GenerateReportArgs:
    """generate_report 业务参数集（v2 pydantic 模型的 dataclass 平移）。"""

    # 要分析的活动编号列表；为 None 时取分析队列中的活动
    activity_ids: list[str] | None = None
    # 数据来源：analysis_queue=分析队列（默认），activity_query=显式指定活动，uploaded=已解析的上传文件
    data_source: Literal["activity_query", "uploaded", "analysis_queue"] = "analysis_queue"
    # 分析指标，如 ['conversion_rate','roi']
    metrics: list[str] | None = None
    # 分析维度，如 ['region','channel']
    dimensions: list[str] | None = None
    # 分析视角：outbound_call_analysis（外呼）/ sms_analysis（短信）/ comprehensive_operations（综合运营）
    perspective: str | None = None
    # 图表类型偏好，如 'bar'、'line'、'pie'
    chart_style: str | None = None
    # 报告主题色偏好
    report_theme: str = ""
    # 自由文本补充分析要求
    analysis_focus: str = ""
    # 外呼视角下混合活动确认：首次调用返回 need_confirm 后，用户确认继续生成时置 true 重新调用
    confirm_mixed: bool = False


class PipelineAbort(Exception):
    """管线内节点按旧约定返回 finalize + final_response 时抛出。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# ── Step A：活动解析 ──

def _resolve_activities(state: dict, args: GenerateReportArgs) -> tuple[list[dict], list[str], str]:
    """返回 (快照命中列表, 未命中编号列表, 错误信息)。错误信息非空则前两者无效。"""
    if args.data_source == "uploaded":
        dataset = state.get("uploaded_activity_dataset") or {}
        activities = dataset.get("activities") or []
        if not activities:
            return [], [], "上传数据尚未解析，请先调用 parse_uploaded_data"
        return activities, [], ""

    if args.activity_ids:
        wanted = [str(aid).strip() for aid in args.activity_ids if str(aid).strip()]
        snapshot_index = {
            activity_key(item): item
            for item in (state.get("activity_list") or [])
            if isinstance(item, dict) and activity_key(item)
        }
        queue_index = {
            str(item.get("activity_id") or ""): item
            for item in (state.get("analysis_queue") or [])
            if isinstance(item, dict) and item.get("activity_id")
        }
        resolved: list[dict] = []
        missing: list[str] = []
        for aid in wanted:
            if aid in snapshot_index:
                resolved.append(snapshot_index[aid])
            elif aid in queue_index:
                resolved.append(queue_index[aid])
            else:
                missing.append(aid)
        return resolved, missing, ""

    queue = [item for item in (state.get("analysis_queue") or []) if isinstance(item, dict)]
    if queue:
        return queue, [], ""
    return [], [], "没有可分析的活动：分析队列为空，且未指定 activity_ids。请先 search_activities 查询并确认要分析的活动"


async def _backfill_missing_activities(missing: list[str], ctx: ToolContext) -> dict[str, dict]:
    """快照/队列未命中的活动编号回源补齐（query_activity_by_id 同款精确匹配）。

    追加活动场景：模型传入"旧活动 + 新活动"完整编号，旧活动却不在最近一次
    搜索快照里（activity_list 只保留最近一次查询结果）。若直接报错，模型要
    重新 search_activities 核实再调 generate_report——多一轮工具调用的同时，
    已有报告时会再多弹一次覆盖审批（联调实测用户被迫确认两次）。
    """
    from src.agent_v3.tools.impl.activity_query import query_activity_by_id

    fetched: dict[str, dict] = {}
    for aid in missing:
        activity, error = await query_activity_by_id(aid, ctx.request)
        if activity is not None:
            fetched[aid] = activity
        else:
            logger.info("generate_report 回源补齐未命中: %s (%s)", aid, error)
    return fetched


async def _resolve_activities_with_backfill(
    state: dict, args: GenerateReportArgs, ctx: ToolContext
) -> tuple[list[dict], str]:
    """快照解析 + 未命中回源补齐，返回 (活动快照列表, 错误信息)。"""
    activities, missing, error = _resolve_activities(state, args)
    if error or not missing:
        return activities, error
    fetched = await _backfill_missing_activities(missing, ctx)
    still_missing = [aid for aid in missing if aid not in fetched]
    if still_missing:
        return [], (
            f"活动 {', '.join(still_missing)} 未查询到，"
            "请先用 search_activities 核实活动编号后再生成报告"
        )
    # 按模型传入的编号顺序合并（回源补齐的只是数据来源不同，语义等价快照命中）
    wanted = [str(aid).strip() for aid in (args.activity_ids or []) if str(aid).strip()]
    by_id = {activity_key(a): a for a in activities}
    by_id.update(fetched)
    return [by_id[aid] for aid in wanted if aid in by_id], ""


OUTBOUND_PERSPECTIVE_KEY = "outbound_call_analysis"


async def _probe_outbound_activities(activities: list[dict], ctx: ToolContext) -> dict[str, dict]:
    """合并调外呼数据接口探测外呼活动；失败回退逐活动探测。

    入参仅活动编号（act_no）+ 用户上下文，不传开始/结束时间（设计文档 §5.1）。
    返回 {activity_key: {"status": "found"|"not_found"|"error", "data": dict, "error": str}}。
    """
    keys: list[str] = []
    for activity in activities:
        key = activity_key(activity)
        if key and key not in keys:
            keys.append(key)
    if not keys:
        return {}
    merged = await _probe_outbound_merged(keys, ctx)
    if merged is not None:
        return merged
    return await _probe_outbound_activities_individually(activities, ctx)


async def _probe_outbound_merged(keys: list[str], ctx: ToolContext) -> dict[str, dict] | None:
    """一次合并调用探测全部活动；成功返回探测结果，失败返回 None（触发回退）。"""
    try:
        result = await asyncio.to_thread(
            fetch_outbound_activity_data,
            {
                "act_no": keys,
                "activity_id": keys,
                "user_id": ctx.request.user_id or "",
                "org_no": ctx.request.org_no or "",
                "channel": ctx.request.channel or "",
            },
        )
    except Exception as exc:  # 网络/超时等按调用失败处理，回退逐活动探测
        logger.warning("外呼合并探测异常，回退逐活动探测: %s", exc)
        return None
    if not result.success:
        logger.warning("外呼合并探测失败，回退逐活动探测: %s", result.error)
        return None
    data = result.data or {}
    matched = data.get("matched_act_nos") if isinstance(data, dict) else None
    if not isinstance(matched, list):  # 旧式响应无法逐活动判定，回退逐活动探测
        logger.warning("外呼合并探测响应缺少 matched_act_nos，回退逐活动探测")
        return None
    matched_set = {str(item) for item in matched}
    return {
        key: {
            "status": "found" if key in matched_set else "not_found",
            "data": _split_outbound_data(data, key) if key in matched_set else {},
            "error": "",
        }
        for key in keys
    }


def _split_outbound_data(data: dict, act_key: str) -> dict:
    """从合并调用的聚合 data 中拆分出单个活动的数据（过滤 sources 行、重算 totalCount）。"""
    sources = data.get("sources")
    if not isinstance(sources, dict):
        return dict(data)
    split_sources: dict[str, dict] = {}
    total = 0
    for trade_code, source in sources.items():
        if not isinstance(source, dict):
            split_sources[trade_code] = source
            continue
        rows = [
            row
            for row in (source.get("result") or [])
            if isinstance(row, dict) and str(row.get("act_no") or "") == act_key
        ]
        split_sources[trade_code] = {**source, "totalCount": len(rows), "result": rows}
        total += len(rows)
    return {
        **data,
        "act_no": act_key,
        "activity_id": act_key,
        "totalCount": total,
        "sources": split_sources,
    }


async def _probe_outbound_activities_individually(activities: list[dict], ctx: ToolContext) -> dict[str, dict]:
    """逐个调外呼数据接口探测活动是否为外呼活动（合并探测失败时的回退路径）。"""

    async def probe(activity: dict) -> tuple[str, dict]:
        key = activity_key(activity)
        try:
            result = await asyncio.to_thread(
                fetch_outbound_activity_data,
                {
                    "act_no": key,
                    "activity_id": key,
                    "user_id": ctx.request.user_id or "",
                    "org_no": ctx.request.org_no or "",
                    "channel": ctx.request.channel or "",
                },
            )
        except Exception as exc:  # 网络/超时等按调用失败处理
            return key, {"status": "error", "data": {}, "error": str(exc)}
        if not result.success:
            return key, {"status": "error", "data": {}, "error": result.error or "调用失败"}
        data = result.data or {}
        found = bool(data and not (isinstance(data, dict) and data.get("matched") is False))
        return key, {
            "status": "found" if found else "not_found",
            "data": data if found else {},
            "error": "",
        }

    pairs = await asyncio.gather(*(probe(activity) for activity in activities))
    return dict(pairs)


# ── Step B：seed 构建（独立可测）──

def _derive_date_range(activities: list[dict], today: date | None = None) -> dict:
    return compute_analysis_period(activities, today or date.today())


def _derive_activity_type(activities: list[dict]) -> str:
    """从活动列表中提取统一的 activity_type。

    收集所有活动的非空 activity_type，去重后：
    - 全部相同 → 返回该值
    - 多种类型 → 返回空字符串（表示混合）
    - 全部为空 → 返回空字符串
    """
    types: set[str] = set()
    for a in activities:
        val = (
            a.get("activity_type")
            or a.get("actTypeCd")
            or a.get("活动类型")
            or ""
        ).strip()
        if val:
            types.add(val)
    if len(types) == 1:
        return next(iter(types))
    return ""


def _build_instruction(args: GenerateReportArgs, original_text: str, activities: list[dict]) -> str:
    parts = [original_text or "生成活动分析报告"]
    if args.metrics:
        parts.append(f"分析指标：{'、'.join(args.metrics)}")
    if args.dimensions:
        parts.append(f"分析维度：{'、'.join(args.dimensions)}")
    if args.perspective and (cfg := get_perspective(args.perspective)):
        parts.append(cfg["prompt_excerpt"])
    if args.chart_style:
        parts.append(f"图表偏好：{args.chart_style}")
    if args.report_theme:
        parts.append(f"报告主题色：{args.report_theme}")
    if args.analysis_focus:
        parts.append(f"补充要求：{args.analysis_focus}")
    names = "、".join(str(a.get("name") or activity_key(a)) for a in activities[:5])
    parts.append(f"目标活动：{names}")
    return "；".join(parts)


def build_report_seed(
    state: dict,
    ctx: ToolContext,
    args: GenerateReportArgs,
    activities: list[dict],
    original_text: str = "",
    *,
    outbound_map: dict | None = None,
    today: date | None = None,
) -> dict:
    """构建报告管线的初始 state。

    契约（配套 tests/agent_v3/test_seed_builder.py 保障）：
    - 以 RUNTIME_STATE_DEFAULTS 为底，确保节点读取的每个键都有默认值；
    - request_id 为每份报告独立 ID（run-history 行按此归集）；
    - report_history_enabled=True + selected_report_activity_ids 触发
      marketing_report_synthesis 内的 create_report_run_history；
    - messages 为纯 dict 消息（agent_run_history_service 按 role/type ∈
      {"human","user"} 解析，与旧框架 HumanMessage 语义一致）。
    """
    period = _derive_date_range(activities, today)
    cfg = get_perspective(args.perspective) if args.perspective else None
    scene = "activity_analysis"
    if cfg:
        # 意图⑧视角注入点：scene 流入 template_matching 相似度与 synthesis 的 _compact_intent
        scene = f"activity_analysis；分析视角：{cfg['prompt_excerpt']}"

    instruction = _build_instruction(args, original_text, activities)
    activity_ids = [activity_key(a) for a in activities if activity_key(a)]

    seed = {
        **RUNTIME_STATE_DEFAULTS,
        "request_id": uuid4().hex,
        "thread_id": ctx.request.thread_id or "",
        "user_id": ctx.request.user_id or "",
        "user_name": ctx.request.user_name or "",
        "org_no": ctx.request.org_no or "",
        "channel": ctx.request.channel or "",
        "messages": [{"role": "user", "content": instruction}],
        "original_user_text": original_text or instruction,
        "marketing_intent": {
            "intent_type": "activity_analysis",
            "activity_type": _derive_activity_type(activities),
            "period": period,
            "scene": scene,
        },
        "activity_list": activities,
        "report_history_enabled": True,
        "selected_report_activity_ids": activity_ids,
        "data_source": args.data_source,
        "perspective_key": args.perspective or "",
        "perspective_keyword": cfg["template_keyword"] if cfg else "",
        "outbound_activity_data_map": dict(outbound_map or {}),
        "workflow_mode": _preset_workflow_mode(args, activities, outbound_map),
    }
    if seed["workflow_mode"] == "direct_outbound_report":
        seed["outbound_activity_data"] = dict((outbound_map or {}).get(activity_key(activities[0])) or {})
        seed["outbound_activity_data_found"] = True
    if args.data_source == "uploaded":
        # generate_report 会以独立 seed 运行旧报告管线，必须显式保留解析工具
        # 写入会话状态的上传数据；其他数据源继续使用运行时默认值。
        seed["uploaded_activity_dataset"] = dict(state.get("uploaded_activity_dataset") or {})
        seed["data_summary"] = state.get("data_summary") or ""
        seed["workflow_key"] = "uploaded_activity_report"
    return seed


def _preset_workflow_mode(
    args: GenerateReportArgs,
    activities: list[dict],
    outbound_map: dict | None,
) -> str:
    """视角驱动的确定性分流（设计文档 §4.5）：seed 预置，编排层优先于路由节点。"""
    if args.perspective == "outbound_call_analysis" and outbound_map and len(activities) == 1:
        return "direct_outbound_report"
    return "template_component_report"


_MAX_PRESET_COMPONENTS = 20


def _normalize_report_components(raw) -> list[dict]:
    """把报告页组件编排步传入的组件（{name, cat, desc, tpl}）归一化为
    build_dependent_components_from_skills 认识的 skill_details 形态。"""
    components: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("skill_name") or "").strip()
        if not name:
            continue
        components.append(
            {
                "name": name,
                "skill_category": str(item.get("cat") or item.get("skill_category") or ""),
                "skill_description": str(
                    item.get("desc") or item.get("skill_description") or item.get("description") or ""
                ),
                "skill_template_preview": str(
                    item.get("tpl") or item.get("skill_template_preview") or ""
                ),
            }
        )
        if len(components) >= _MAX_PRESET_COMPONENTS:
            break
    return components


def _build_preset_framework_match(components: list[dict], activities: list[dict]) -> dict:
    """用组件编排步预选的组件直接构造活动模板匹配结果（source=user_selected_components），
    字段与 activity_template_matching 输出一致，下游合成/trace 渲染零改动。"""
    names = [component["name"] for component in components]
    return {
        "template_id": "",
        "template_name": "用户自选分析框架",
        "activity_ids": [activity_key(a) for a in activities if activity_key(a)],
        "skill_sequence": names,
        "skill_details": components,
        "dependent_components": build_dependent_components_from_skills(names, components),
        "reasoning": f"使用组件编排步骤选定的 {len(names)} 个分析组件，未做活动模板匹配",
        "source": "user_selected_components",
    }


# ── Step C：内部管线编排 ──

# 步骤完成时透传给前端思维面板的业务数据白名单（对齐 v2 trace 面板的 step payload
# 契约：前端按 step.node + payload 渲染匹配模板/分析能力等详情）。未列出的步骤
# 不携带 payload，避免把整包 state 推流。
_STEP_TRACE_PAYLOAD_KEYS = {
    "selected_activity_router": ("activity_route_result", "workflow_mode", "activity_list"),
    "outbound_activity_data_fetch": ("outbound_activity_data_found",),
    "template_list_fetch": ("template_list",),
    "template_matching": ("template_match_result", "matched_data_templates"),
    "component_value_fetch": (),
    "component_value_cleanup": ("component_value_cleanup_result",),
    "activity_template_matching": ("activity_template_match_result",),
}

# 组件取数 trace 摘要上限：供前端 chips 展示，避免 trace 帧携带整个 component_values 大对象
_MAX_TRACE_FETCH_METRICS = 20
_MAX_TRACE_FETCH_TEMPLATES = 10


def _count_fetched_metrics(value) -> int:
    """组件取数值的指标计数：list 为板块列表（板块内含指标明细），dict 为指标→数值。"""
    if isinstance(value, list):
        return sum(
            len(plate.get("plateShowIndCfgInfDtoList") or [])
            for plate in value
            if isinstance(plate, dict)
        )
    if isinstance(value, dict):
        return len(value)
    return 1


def _component_value_fetch_summary(state: dict) -> dict:
    """组件数值获取的紧凑 trace 摘要：指标总数 + 按数据模板分组明细 + 取数失败数。

    component_values 的合并键有两种形态：按模板分组（键为 template_id，值是板块
    列表）时借助 template_component_values 取模板名；未分组的键（dict 合并分支）
    直接作为指标名展示，"template_id:指标" 冲突键去掉模板前缀。
    """
    payload = state.get("component_values") or {}
    values = payload.get("component_values")
    errors = payload.get("errors") or []
    if not isinstance(values, dict):
        values = {}
    meta = payload.get("template_component_values")
    meta = meta if isinstance(meta, dict) else {}

    templates: list[dict] = []
    loose_metrics: list[str] = []
    for key, value in values.items():
        info = meta.get(key)
        if isinstance(info, dict):
            templates.append({
                "template_name": info.get("template_name") or str(key),
                "metric_count": _count_fetched_metrics(value),
            })
            continue
        name = str(key)
        prefix, _, rest = name.partition(":")
        if rest and prefix in meta:
            name = rest
        loose_metrics.append(name)

    return {
        "metric_count": sum(t["metric_count"] for t in templates) + len(loose_metrics),
        "templates": templates[:_MAX_TRACE_FETCH_TEMPLATES],
        "metrics": sorted(loose_metrics)[:_MAX_TRACE_FETCH_METRICS],
        "error_count": len(errors) if isinstance(errors, list) else 0,
    }


def _step_trace_payload(name: str, state: dict) -> dict:
    if name not in _STEP_TRACE_PAYLOAD_KEYS:
        return {}
    # False/0 是合法业务值（如 outbound_activity_data_found=False），只过滤空容器
    keys = _STEP_TRACE_PAYLOAD_KEYS[name]
    payload = {key: state[key] for key in keys if state.get(key) not in (None, "", [], {})}
    if name == "component_value_fetch":
        summary = _component_value_fetch_summary(state)
        if summary["metric_count"] or summary["error_count"]:
            payload["component_value_fetch_summary"] = summary
    return payload


async def run_report_pipeline(seed: dict, writer=lambda _event: None) -> dict:
    """按旧工作流顺序调用原节点函数（async）。失败约定转换为 PipelineAbort。"""
    s = dict(seed)
    data_source = s.get("data_source")
    is_uploaded = data_source == "uploaded"

    async def step(name: str, fn) -> None:
        writer({"step": name, "status": "running"})
        t0 = time.monotonic()
        try:
            update = await fn(s)
        except Exception as exc:
            if is_timeout_exception(exc):
                logger.error(
                    "generate_report 步骤超时: step=%s request_id=%s error=%s elapsed=%.2fs",
                    name,
                    s.get("request_id", ""),
                    summarize(str(exc), 200),
                    time.monotonic() - t0,
                )
            raise
        if isinstance(update, dict):
            s.update(update)
        logger.info("generate_report 步骤完成: %s (%.2fs)", name, time.monotonic() - t0)
        # 旧节点失败约定：next_agent=finalize 且非末步
        if s.get("next_agent") == "finalize" and name != "marketing_report_synthesis":
            raise PipelineAbort(s.get("final_response") or f"{name} 执行失败")
        done_event = {"step": name, "status": "done"}
        trace_payload = _step_trace_payload(name, s)
        if trace_payload:
            done_event["payload"] = trace_payload
        writer(done_event)

    preset_mode = s.get("workflow_mode") or ""
    await step("selected_activity_router", selected_activity_router_node)
    if preset_mode:
        # seed 预置的视角分流优先于路由节点（设计文档 §4.5）
        s["workflow_mode"] = preset_mode

    # 上传数据不查银行外呼接口，强制走模板组件分支
    if is_uploaded:
        s["workflow_mode"] = "template_component_report"

    if s.get("workflow_mode") == "single_activity_outbound_first" and not is_uploaded:
        await step("outbound_activity_data_fetch", outbound_activity_data_fetch_node)

    # 报告页「组件编排」预选了分析组件时，跳过活动模板匹配，直接按预选框架编排报告；
    # 复用同名 step 发 trace 帧，前端渲染「报告分析框架」卡片（用户自选分析框架）。
    preset_components = _normalize_report_components(s.get("preset_analysis_components"))

    async def preset_framework_step(_state) -> dict:
        return {
            "activity_template_match_result": _build_preset_framework_match(
                preset_components, s.get("activity_list") or []
            )
        }

    activity_template_matched = False
    if s.get("workflow_mode") != "direct_outbound_report":
        if not is_uploaded:
            await step("template_list_fetch", template_list_fetch_node)
            await step("template_matching", template_matching_node)
            await step("component_value_fetch", component_value_fetch_node)
        else:
            # 上传文件分支依赖活动模板来组织组件指标，保持与主线工作流一致：
            # 先匹配活动模板，再提取上传数据组件值。
            if preset_components:
                await step("activity_template_matching", preset_framework_step)
            else:
                await step("activity_template_matching", activity_template_matching_node)
            activity_template_matched = True
            await step("uploaded_component_value_extract", uploaded_component_value_extract_node)
        await step("component_value_cleanup", component_value_cleanup_node)
        if s.get("outbound_activity_data_map"):
            # 合并在 cleanup 之后，避免外呼数据被空值清洗误删（设计文档 §5.3）
            s["component_values"] = _merge_outbound_into_component_values(
                s.get("component_values") or {},
                s["outbound_activity_data_map"],
            )
        await step("branch_drilldown", branch_drilldown_node)

    if not activity_template_matched:
        if preset_components:
            await step("activity_template_matching", preset_framework_step)
        else:
            await step("activity_template_matching", activity_template_matching_node)

    # 合成 + HTML 守卫重试循环（复刻 report_html_guard_node 契约：
    # 失败 → 记录 issues + 清空 html_report → 合成节点自动注入重试指令）
    max_retries = max(0, int(get_settings().report_html_guard_max_retries))
    for attempt in range(max_retries + 1):
        await step("marketing_report_synthesis", marketing_report_synthesis_node)
        html = s.get("html_report") or ""
        if s.get("next_agent") == "finalize" and not html:
            raise PipelineAbort(s.get("final_response") or "报告生成失败")
        result = validate_report_html(html)
        if result.valid:
            _asset_name, version_no = save_report_file(s["request_id"], html)
            s["report_version_no"] = version_no
            s["report_html_guard_result"] = result.to_dict(
                retry_count=attempt,
                max_retries=max_retries,
            )
            return s
        logger.info(
            "generate_report HTML 校验未通过 (attempt %d/%d)",
            attempt + 1,
            max_retries + 1,
        )
        s["report_html_guard_result"] = result.to_dict(
            retry_count=attempt + 1,
            max_retries=max_retries,
        )
        s["html_report"] = ""

    s["pipeline_failed"] = True
    return s


def _merge_outbound_into_component_values(component_values: dict, outbound_map: dict) -> dict:
    """把外呼接口数据按 outbound:<act_no> 命名空间并入组件数值（设计文档 §5.3）。"""
    merged = dict(component_values)
    inner = dict(merged.get("component_values") or {})
    registry = dict(merged.get("template_component_values") or {})
    for act_key, data in outbound_map.items():
        if not data:
            continue
        inner[f"outbound:{act_key}"] = data
        registry[f"outbound:{act_key}"] = {
            "template_id": f"outbound:{act_key}",
            "template_name": "外呼活动数据",
            "source": "outbound_activity_api",
            "params": {"act_no": act_key},
            "values": data,
        }
    merged["component_values"] = inner
    merged["template_component_values"] = registry
    return merged


def _with_uploaded_failure_guidance(data_source: str, message: str) -> str:
    if data_source != "uploaded":
        return message
    return (
        f"{message}。当前请求仍使用上传文件数据源，请直接向用户说明该错误并停止；"
        "不要调用 search_activities，也不要切换为系统在线活动数据源"
    )


# ── Step D：工具入口 ──

async def generate_report(
    ctx: ToolContext,
    activity_ids: list[str] | None = None,
    data_source: Literal["activity_query", "uploaded", "analysis_queue"] = "analysis_queue",
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
    perspective: str | None = None,
    chart_style: str | None = None,
    report_theme: str = "",
    analysis_focus: str = "",
    confirm_mixed: bool = False,
) -> str | ToolOutcome:
    """为指定活动生成 HTML 分析报告。可指定分析指标、维度、视角等参数；
    更换指标/维度/视角重新分析时，用新参数再次调用本工具。"""
    if perspective and not get_perspective(perspective):
        return error_content(f"未知分析视角 {perspective}，可选：{perspective_keys_text()}")

    args = GenerateReportArgs(
        activity_ids=activity_ids,
        data_source=data_source,
        metrics=metrics,
        dimensions=dimensions,
        perspective=perspective,
        chart_style=chart_style,
        report_theme=report_theme,
        analysis_focus=analysis_focus,
        confirm_mixed=confirm_mixed,
    )

    state = ctx.state

    activities, error = await _resolve_activities_with_backfill(state, args, ctx)
    if error:
        return error_content(error)

    outbound_map: dict[str, dict] = {}
    if args.perspective == OUTBOUND_PERSPECTIVE_KEY and args.data_source != "uploaded":
        probe = await _probe_outbound_activities(activities, ctx)
        status_of = {activity_key(a): probe.get(activity_key(a), {}).get("status") for a in activities}
        if all(status == "error" for status in status_of.values()):
            first_error = next(v["error"] for v in probe.values() if v["status"] == "error")
            return error_content(f"外呼活动数据查询失败：{summarize(first_error, 120)}")

        outbound_map = {k: v["data"] for k, v in probe.items() if v["status"] == "found"}
        if not outbound_map:
            return error_content("所选的活动均不是外呼活动，无法使用外呼渠道视角进行分析")

        non_outbound = [a for a in activities if status_of.get(activity_key(a)) != "found"]
        if len(activities) > 1 and non_outbound and not args.confirm_mixed:
            failed_names = [
                activity_name(a) for a in non_outbound if status_of.get(activity_key(a)) == "error"
            ]
            names = [activity_name(a) for a in non_outbound]
            message = (
                f"以下活动不是外呼活动：{'、'.join(names)}。"
                "是否继续生成报告？非外呼活动将使用数据模板取数，报告采用多活动分析模板。"
            )
            if failed_names:
                message += f"（其中 {'、'.join(failed_names)} 外呼数据查询失败，按非外呼活动处理）"
            logger.info(
                "generate_report 外呼视角混合活动待确认: outbound=%s non_outbound=%s",
                list(outbound_map),
                names,
            )
            return ok_content(
                {
                    "status": "need_confirm",
                    "message": message,
                    "non_outbound_activities": names,
                    "non_outbound_query_failed": failed_names,
                    "outbound_activities": [
                        activity_name(a) for a in activities if status_of.get(activity_key(a)) == "found"
                    ],
                }
            )

    # turn 级键只从 ToolContext.request 读取（壳层不再注入 state 快照）
    original_text = str(ctx.request.original_user_text or "")
    # 报告页组件编排预选组件：本轮请求显式传入优先，否则沿用会话中保存的 preset
    # （报告页后续追问重新生成时继续生效）；/chat-ui 两者皆空，走原模板匹配。
    preset_components = _normalize_report_components(
        ctx.request.report_components
    ) or _normalize_report_components(ctx.state.get("preset_analysis_components"))
    seed = build_report_seed(state, ctx, args, activities, original_text, outbound_map=outbound_map)
    if preset_components:
        seed["preset_analysis_components"] = preset_components
    writer = ctx.write_stream

    pipeline_started = time.monotonic()
    try:
        # 管线放在独立线程的事件循环里跑：节点内含同步 DB/LLM 调用，
        # 避免长时间阻塞主事件循环；writer 为同步闭包，线程安全由注入方保证。
        result = await asyncio.to_thread(lambda: asyncio.run(run_report_pipeline(seed, writer)))
    except PipelineAbort as abort:
        logger.info("generate_report 管线中止: %s", abort.message)
        _finish_report_run(seed, pipeline_started, "failed", abort.message)
        user_message = (
            MODEL_BUSY_MESSAGE
            if abort.message == MODEL_BUSY_MESSAGE
            else _with_uploaded_failure_guidance(args.data_source, abort.message)
        )
        return error_content(user_message)
    except Exception as exc:
        duration_ms = int((time.monotonic() - pipeline_started) * 1000)
        if is_context_length_exception(exc):
            logger.error(
                "generate_report 因提示词超过模型上下文中断: "
                "request_id=%s thread_id=%s data_source=%s activities=%s duration_ms=%d error=%s",
                seed.get("request_id", ""),
                seed.get("thread_id", ""),
                args.data_source,
                len(activities),
                duration_ms,
                summarize(str(exc), 200),
            )
            _finish_report_run(seed, pipeline_started, "failed", MODEL_BUSY_MESSAGE)
            return error_content(MODEL_BUSY_MESSAGE)
        if is_timeout_exception(exc):
            logger.error(
                "generate_report 因访问大模型超时中断: "
                "request_id=%s thread_id=%s data_source=%s activities=%s duration_ms=%d error=%s",
                seed.get("request_id", ""),
                seed.get("thread_id", ""),
                args.data_source,
                len(activities),
                duration_ms,
                summarize(str(exc), 200),
            )
            _finish_report_run(seed, pipeline_started, "failed", f"大模型访问超时：{exc}")
            return error_content(
                _with_uploaded_failure_guidance(
                    args.data_source,
                    f"大模型访问超时，请稍后重试：{summarize(str(exc), 120)}",
                )
            )
        logger.exception("generate_report 管线异常")
        _finish_report_run(seed, pipeline_started, "failed", f"报告生成过程异常：{exc}")
        return error_content(
            _with_uploaded_failure_guidance(
                args.data_source,
                f"报告生成过程异常：{summarize(str(exc), 120)}",
            )
        )

    if result.get("pipeline_failed") or not result.get("html_report"):
        _finish_report_run(
            seed,
            pipeline_started,
            "failed",
            f"报告生成多次未通过展示校验：{REPORT_HTML_GUARD_FAILURE_MESSAGE}",
        )
        return error_content(
            _with_uploaded_failure_guidance(
                args.data_source,
                f"报告生成多次未通过展示校验：{REPORT_HTML_GUARD_FAILURE_MESSAGE}",
            )
        )

    _finish_report_run(seed, pipeline_started, "success", "", final_response="活动分析报告已生成")

    html = result["html_report"]
    activity_template = result.get("activity_template_match_result") or {}
    data_templates = result.get("matched_data_templates") or []
    activity_ids = [activity_key(a) for a in activities if activity_key(a)]
    version_no = result.get("report_version_no")

    report_context = {
        "report_id": seed["request_id"],
        "request_id": seed["request_id"],
        "file_path": f"activity-analysis-report-{seed['request_id']}.html",
        "version": 1,
        "version_no": version_no,
        "history": [
            {
                "version": 1,
                "action": "generate",
                "diff_summary": _diff_summary(args, activities),
            }
        ],
        "perspective": args.perspective or "",
        "status": "active",
        "data_snapshot": {
            "activity_ids": activity_ids,
            "activity_names": [str(a.get("name") or "") for a in activities],
            "data_templates": [
                str(t.get("template_name") or t.get("template_id") or "")
                for t in data_templates
                if isinstance(t, dict)
            ],
            "activity_template": str(activity_template.get("template_name") or ""),
            "metrics": args.metrics or [],
            "dimensions": args.dimensions or [],
        },
    }

    content = ok_content(
        {
            "status": "ok",
            "report_id": seed["request_id"],
            "version_no": version_no,
            "activities": len(activities),
            "activity_template": report_context["data_snapshot"]["activity_template"],
            "html_chars": len(html),
            "note": "报告已生成并通过展示校验，将直接展示给用户",
        }
    )
    return ToolOutcome(
        content,
        {
            "html_report": html,
            "report_context": report_context,
            "report_html_guard_result": result.get("report_html_guard_result") or {},
            # 持久化预选组件，报告页后续追问重新生成时继续按自选框架编排
            "preset_analysis_components": preset_components,
        },
    )


def _finish_report_run(
    seed: dict,
    started: float,
    status: str,
    failure_reason: str,
    final_response: str = "",
) -> None:
    """落终态到报告 run-history 行。

    行由管线内 create_report_run_history 按 seed request_id 创建；
    若管线在合成前中止（行未创建），finish_run_history 安全空转。
    """
    from src.services.agent_run_history_service import finish_run_history

    duration_ms = int((time.monotonic() - started) * 1000)
    final_values = {"final_response": final_response} if final_response else None
    finish_run_history(seed["request_id"], status, duration_ms, final_values, failure_reason)


def _diff_summary(args: GenerateReportArgs, activities: list[dict]) -> str:
    parts = [f"对 {len(activities)} 个活动生成报告"]
    if args.metrics:
        parts.append(f"指标：{'、'.join(args.metrics)}")
    if args.dimensions:
        parts.append(f"维度：{'、'.join(args.dimensions)}")
    if args.perspective and (cfg := get_perspective(args.perspective)):
        parts.append(f"视角：{cfg['display_name']}")
    return "；".join(parts)
