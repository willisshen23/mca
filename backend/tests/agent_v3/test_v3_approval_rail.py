"""ApprovalEditRail 三决策单元测试（直接调 resolve_interrupt，不起 agent）。"""

import json
from types import SimpleNamespace

import pytest

from openjiuwen.core.foundation.llm.schema.tool_call import ToolCall
from openjiuwen.harness.rails.interrupt.interrupt_base import (
    ApproveResult, InterruptResult, RejectResult,
)

from src.agent_v3.rails import ApprovalEditRail


def _ctx():
    return SimpleNamespace(extra={}, session=None)


def _tool_call():
    return ToolCall(id="call-1", type="function", name="modify_report",
                    arguments='{"free_instruction":"改标题"}', index=0)


async def test_first_call_interrupts():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(_ctx(), _tool_call(), None, None)
    assert isinstance(decision, InterruptResult)
    schema = decision.request.payload_schema
    assert "decision" in schema.get("properties", {})


async def test_approve():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(
        _ctx(), _tool_call(), {"decision": "approve"}, None)
    assert isinstance(decision, ApproveResult)
    assert decision.new_args is None


async def test_edit_rewrites_args_as_json_string():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    edited = {"free_instruction": "改成中文标题"}
    decision = await rail.resolve_interrupt(
        _ctx(), _tool_call(), {"decision": "edit", "edited_args": edited}, None)
    assert isinstance(decision, ApproveResult)
    assert json.loads(decision.new_args) == edited
    assert isinstance(decision.new_args, str)


async def test_reject_carries_feedback_and_no_retry_guidance():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(
        _ctx(), _tool_call(), {"decision": "reject", "message": "先别改"}, None)
    assert isinstance(decision, RejectResult)
    assert "先别改" in str(decision.tool_result)
    assert "不要再调用" in str(decision.tool_result)


async def test_unparseable_input_reinterrupts():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(_ctx(), _tool_call(), {"foo": 1}, None)
    assert isinstance(decision, InterruptResult)


async def test_interrupt_message_uses_tool_display_name():
    """审批文案按工具定制（对齐 v2 interrupt_on）：modify_report → 修改报告。"""
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(_ctx(), _tool_call(), None, None)
    assert isinstance(decision, InterruptResult)
    assert decision.request.message == "请确认是否执行「修改报告」"


async def test_interrupt_message_falls_back_when_tool_call_is_none():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(_ctx(), None, None, None)
    assert isinstance(decision, InterruptResult)
    assert decision.request.message == "请确认是否执行该操作"
