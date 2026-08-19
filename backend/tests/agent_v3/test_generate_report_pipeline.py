"""generate_report 内部管线编排测试（mock 9 个节点函数与守卫，无 LLM/网络；指向 agent_v3 impl 层）。

锁定：
- 节点调用顺序（router → outbound(单活动) → 模板链 → 活动模板 → 合成）
- direct_outbound_report 模式跳过模板链
- HTML 守卫重试循环与耗尽路径
- 节点失败约定（next_agent=finalize）→ PipelineAbort
- LLM 超时异常被识别并记录
"""
from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import report_gen as rg


def _make_node(name, calls, update):
    async def node(state):
        calls.append(name)
        return dict(update)

    return node


def _guard_valid():
    return SimpleNamespace(
        valid=True,
        issues=[],
        to_dict=lambda *, retry_count, max_retries: {"valid": True, "retry_count": retry_count},
    )


def _guard_invalid(issue="缺少 body 标签"):
    return SimpleNamespace(
        valid=False,
        issues=[issue],
        to_dict=lambda *, retry_count, max_retries: {
            "valid": False,
            "retry_count": retry_count,
            "issues": [issue],
        },
    )


def _patch_pipeline(monkeypatch, calls, *, outbound_mode="template_component_report", synth_html="<html><body>ok</body></html>"):
    monkeypatch.setattr(
        rg,
        "selected_activity_router_node",
        _make_node("selected_activity_router", calls, {"workflow_mode": outbound_mode, "next_agent": "x"}),
    )
    monkeypatch.setattr(
        rg,
        "outbound_activity_data_fetch_node",
        _make_node("outbound_activity_data_fetch", calls, {"next_agent": "x"}),
    )
    monkeypatch.setattr(rg, "template_list_fetch_node", _make_node("template_list_fetch", calls, {"next_agent": "x"}))
    monkeypatch.setattr(rg, "template_matching_node", _make_node("template_matching", calls, {"next_agent": "x"}))
    monkeypatch.setattr(rg, "component_value_fetch_node", _make_node("component_value_fetch", calls, {"next_agent": "x"}))
    monkeypatch.setattr(rg, "component_value_cleanup_node", _make_node("component_value_cleanup", calls, {"next_agent": "x"}))
    monkeypatch.setattr(rg, "branch_drilldown_node", _make_node("branch_drilldown", calls, {"next_agent": "x"}))
    monkeypatch.setattr(rg, "activity_template_matching_node", _make_node("activity_template_matching", calls, {"next_agent": "x"}))
    monkeypatch.setattr(
        rg,
        "marketing_report_synthesis_node",
        _make_node("marketing_report_synthesis", calls, {"html_report": synth_html, "next_agent": "supervisor"}),
    )


def test_pipeline_step_done_events_carry_trace_payloads(monkeypatch):
    """步骤 done 帧需携带业务数据（前端思维面板按 step payload 渲染，对齐 v2 契约）。"""
    calls = []
    _patch_pipeline(monkeypatch, calls)
    monkeypatch.setattr(
        rg,
        "template_matching_node",
        _make_node("template_matching", calls, {
            "next_agent": "x",
            "template_match_result": {"template_id": "DT-1", "template_name": "模板A"},
            "matched_data_templates": [{"template_id": "DT-1"}],
        }),
    )
    monkeypatch.setattr(
        rg,
        "activity_template_matching_node",
        _make_node("activity_template_matching", calls, {
            "next_agent": "x",
            "activity_template_match_result": {"template_id": "AT-1"},
        }),
    )
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))

    events = []
    asyncio.run(rg.run_report_pipeline({"request_id": "r-trace"}, writer=events.append))

    done = {e["step"]: e for e in events if e["status"] == "done"}
    assert done["template_matching"]["payload"]["template_match_result"]["template_id"] == "DT-1"
    assert done["template_matching"]["payload"]["matched_data_templates"] == [{"template_id": "DT-1"}]
    assert done["activity_template_matching"]["payload"]["activity_template_match_result"]["template_id"] == "AT-1"
    # 未配置白名单的步骤不携带 payload，避免整包 state 推流
    assert "payload" not in done["component_value_fetch"]


def test_pipeline_call_order_multi_activity(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls)
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_valid())
    saved = []
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: saved.append(request_id) or ("asset.html", 1))

    events = []
    result = asyncio.run(rg.run_report_pipeline({"request_id": "r-1"}, writer=events.append))

    assert calls == [
        "selected_activity_router",
        "template_list_fetch",
        "template_matching",
        "component_value_fetch",
        "component_value_cleanup",
        "branch_drilldown",
        "activity_template_matching",
        "marketing_report_synthesis",
    ]
    assert result["html_report"].startswith("<html>")
    assert result["report_html_guard_result"]["valid"] is True
    assert saved == ["r-1"]
    # writer 进度事件覆盖每个步骤
    steps = [e["step"] for e in events if e["status"] == "running"]
    assert steps == calls


def test_pipeline_single_activity_outbound_first(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls, outbound_mode="single_activity_outbound_first")
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))

    asyncio.run(rg.run_report_pipeline({"request_id": "r-2"}))

    assert "outbound_activity_data_fetch" in calls
    assert calls.index("outbound_activity_data_fetch") < calls.index("template_list_fetch")


def test_pipeline_direct_outbound_skips_template_chain(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls, outbound_mode="direct_outbound_report")
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))

    asyncio.run(rg.run_report_pipeline({"request_id": "r-3"}))

    assert calls == [
        "selected_activity_router",
        "activity_template_matching",
        "marketing_report_synthesis",
    ]


def test_pipeline_guard_retry_then_pass(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls)
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))
    outcomes = iter([_guard_invalid(), _guard_valid()])
    monkeypatch.setattr(rg, "validate_report_html", lambda html: next(outcomes))

    result = asyncio.run(rg.run_report_pipeline({"request_id": "r-4"}))

    # 合成被调用两次（首次校验失败 → 重试通过）
    assert calls.count("marketing_report_synthesis") == 2
    assert result.get("pipeline_failed") is not True


def test_pipeline_guard_exhausted(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls)
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_invalid())
    # 默认 report_html_guard_max_retries=1 → 最多 2 次合成
    result = asyncio.run(rg.run_report_pipeline({"request_id": "r-5"}))

    assert calls.count("marketing_report_synthesis") == 2
    assert result["pipeline_failed"] is True


def test_pipeline_abort_on_node_failure(monkeypatch):
    calls = []

    async def failing_template_match(state):
        calls.append("template_matching")
        return {"next_agent": "finalize", "final_response": "未匹配到可用数据模板"}

    _patch_pipeline(monkeypatch, calls)
    monkeypatch.setattr(rg, "template_matching_node", failing_template_match)

    with pytest.raises(rg.PipelineAbort) as exc_info:
        asyncio.run(rg.run_report_pipeline({"request_id": "r-6"}))

    assert "未匹配到可用数据模板" in exc_info.value.message
    # 失败节点之后的步骤不得执行
    assert "component_value_fetch" not in calls


def test_pipeline_uploaded_source_skips_remote_apis(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls)
    monkeypatch.setattr(
        rg,
        "uploaded_component_value_extract_node",
        _make_node("uploaded_component_value_extract", calls, {"next_agent": "x"}),
    )
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))

    seed = {"request_id": "r-up", "data_source": "uploaded"}
    asyncio.run(rg.run_report_pipeline(seed))

    assert "template_list_fetch" not in calls
    assert "component_value_fetch" not in calls
    assert "uploaded_component_value_extract" in calls


class FakeLLMTimeoutError(Exception):
    """模拟大模型访问超时异常。"""

    pass


def test_pipeline_step_timeout_is_logged_and_propagated(monkeypatch, caplog):
    """管线步骤触发超时时，应记录步骤级超时日志并继续抛出异常。"""
    calls = []
    _patch_pipeline(monkeypatch, calls)

    async def timeout_synthesis(state):
        calls.append("marketing_report_synthesis")
        raise FakeLLMTimeoutError("ReadTimeout: request timed out after 60s")

    monkeypatch.setattr(rg, "marketing_report_synthesis_node", timeout_synthesis)

    with caplog.at_level(logging.ERROR, logger="njbank.agent"):
        with pytest.raises(FakeLLMTimeoutError):
            asyncio.run(rg.run_report_pipeline({"request_id": "r-timeout"}))

    assert any("generate_report 步骤超时" in rec.message for rec in caplog.records)
    assert any("marketing_report_synthesis" in rec.message for rec in caplog.records)


def test_generate_report_tool_handles_llm_timeout(monkeypatch, caplog):
    """generate_report 工具入口捕获超时后应记录报告级超时事件并返回超时错误。"""
    state = {
        "analysis_queue": [{"activity_id": "act-1", "name": "测试活动"}],
        "original_user_text": "生成报告",
    }
    ctx = ToolContext(
        state=state,
        request=ToolRequestContext(user_id="u1", thread_id="t-1"),
        tool_call_id="call-timeout",
    )

    async def timeout_pipeline(seed, writer):
        raise FakeLLMTimeoutError("APITimeoutError: request timed out")

    monkeypatch.setattr(rg, "run_report_pipeline", timeout_pipeline)
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))

    with caplog.at_level(logging.ERROR, logger="njbank.agent"):
        content = asyncio.run(rg.generate_report(ctx))

    assert content.startswith("ERROR:")
    assert "超时" in content
    assert any(
        "generate_report 因访问大模型超时中断" in rec.message for rec in caplog.records
    )
    assert any("t-1" in rec.message for rec in caplog.records)


def test_generate_report_tool_hides_context_limit_error(monkeypatch, caplog):
    """模型端仍返回上下文超限时，前端只收到统一繁忙提示。"""
    state = {
        "analysis_queue": [{"activity_id": "act-1", "name": "测试活动"}],
        "original_user_text": "生成报告",
    }
    ctx = ToolContext(
        state=state,
        request=ToolRequestContext(user_id="u1", thread_id="t-1"),
        tool_call_id="call-context-limit",
    )

    async def context_limit_pipeline(seed, writer):
        raise RuntimeError("context_length_exceeded: maximum context length is 262144 tokens")

    monkeypatch.setattr(rg, "run_report_pipeline", context_limit_pipeline)

    with caplog.at_level(logging.ERROR, logger="njbank.agent"):
        content = asyncio.run(rg.generate_report(ctx))

    assert content == "ERROR: 系统正忙，请稍后重试"
    assert any("提示词超过模型上下文" in rec.message for rec in caplog.records)


def test_pipeline_preset_workflow_mode_overrides_router(monkeypatch):
    """seed 预置 template_component_report 时，路由节点返回的 single_activity_outbound_first 不得生效。"""
    calls = []
    _patch_pipeline(monkeypatch, calls, outbound_mode="single_activity_outbound_first")
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))

    asyncio.run(rg.run_report_pipeline({"request_id": "r-preset", "workflow_mode": "template_component_report"}))

    assert "outbound_activity_data_fetch" not in calls
    assert "template_list_fetch" in calls


def test_pipeline_direct_outbound_preset_skips_fetch_and_template_chain(monkeypatch):
    """外呼视角单活动命中：seed 预置 direct_outbound_report，跳过外呼查询节点与模板链。"""
    calls = []
    _patch_pipeline(monkeypatch, calls, outbound_mode="single_activity_outbound_first")
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))

    asyncio.run(rg.run_report_pipeline({"request_id": "r-direct", "workflow_mode": "direct_outbound_report"}))

    assert calls == ["selected_activity_router", "activity_template_matching", "marketing_report_synthesis"]


def test_pipeline_merges_outbound_map_after_cleanup(monkeypatch):
    calls = []
    _patch_pipeline(monkeypatch, calls)
    monkeypatch.setattr(rg, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rg, "save_report_file", lambda request_id, html: ("asset.html", 1))

    seed = {
        "request_id": "r-merge",
        "workflow_mode": "template_component_report",
        "outbound_activity_data_map": {"act-1": {"接通率": 0.6}},
    }
    result = asyncio.run(rg.run_report_pipeline(seed))

    assert "outbound_activity_data_fetch" not in calls
    merged = result["component_values"]["component_values"]
    assert merged["outbound:act-1"] == {"接通率": 0.6}
    registry = result["component_values"]["template_component_values"]["outbound:act-1"]
    assert registry["source"] == "outbound_activity_api"
    assert registry["params"] == {"act_no": "act-1"}


def test_merge_outbound_into_component_values_unit():
    component_values = {
        "component_values": {"转化率": [1, 2]},
        "template_component_values": {"tpl-1": {"template_id": "tpl-1"}},
    }
    merged = rg._merge_outbound_into_component_values(component_values, {"act-9": {"挂机率": 0.1}})
    assert merged["component_values"]["转化率"] == [1, 2]
    assert merged["component_values"]["outbound:act-9"] == {"挂机率": 0.1}
    assert merged["template_component_values"]["outbound:act-9"]["source"] == "outbound_activity_api"
    # 空数据不并入
    merged2 = rg._merge_outbound_into_component_values(component_values, {"act-10": {}})
    assert "outbound:act-10" not in merged2["component_values"]
