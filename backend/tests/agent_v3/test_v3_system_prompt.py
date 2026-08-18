"""System Prompt 关键协议回归测试。"""
from __future__ import annotations

from src.agent_v3.prompts import system as system_prompt_module
from src.agent_v3.prompts.system import AGENT_V2_SYSTEM_PROMPT, build_system_prompt

SINGLE_ACTIVITY_RULE_FRAGMENT = 'perspective="comprehensive_operations"'


def test_system_prompt_documents_need_confirm_protocol():
    assert "need_confirm" in AGENT_V2_SYSTEM_PROMPT
    assert "confirm_mixed" in AGENT_V2_SYSTEM_PROMPT


def test_fallback_prompt_documents_single_activity_default_perspective():
    """单活动 + 未指定视角 → 免确认，默认综合运营分析视角。"""
    assert "单活动报告免确认规则" in AGENT_V2_SYSTEM_PROMPT
    assert "只返回一个活动" in AGENT_V2_SYSTEM_PROMPT
    assert SINGLE_ACTIVITY_RULE_FRAGMENT in AGENT_V2_SYSTEM_PROMPT


def test_build_system_prompt_does_not_duplicate_rule(monkeypatch):
    """兜底 prompt 已含规则时，build_system_prompt 不得重复追加。"""
    monkeypatch.setattr(
        system_prompt_module, "get_runtime_prompt", lambda key, fallback: fallback
    )
    prompt = build_system_prompt()
    assert prompt.count(SINGLE_ACTIVITY_RULE_FRAGMENT) == 1


def test_build_system_prompt_appends_rule_to_db_override(monkeypatch):
    """DB 定制 prompt 缺少规则时必须追加，保证线上覆盖不丢该行为。"""
    monkeypatch.setattr(
        system_prompt_module, "get_runtime_prompt", lambda key, fallback: "你是营销分析助手。"
    )
    prompt = build_system_prompt()
    assert "单活动报告默认视角规则" in prompt
    assert SINGLE_ACTIVITY_RULE_FRAGMENT in prompt

