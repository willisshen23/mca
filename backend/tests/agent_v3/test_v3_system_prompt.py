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


PRESET_COMPONENTS_RULE_FRAGMENT = "分析框架请包含以下组件"
KNOWN_TOOLS_RULE_FRAGMENT = "禁止编造或猜测工具名"


def test_fallback_prompt_documents_preset_components_rule():
    """报告页预选组件已自动传入管线，模型不得幻觉"匹配模板/匹配组件"类工具。"""
    assert PRESET_COMPONENTS_RULE_FRAGMENT in AGENT_V2_SYSTEM_PROMPT
    assert "这类工具不存在" in AGENT_V2_SYSTEM_PROMPT
    assert KNOWN_TOOLS_RULE_FRAGMENT in AGENT_V2_SYSTEM_PROMPT


def test_build_system_prompt_does_not_duplicate_preset_rules(monkeypatch):
    monkeypatch.setattr(
        system_prompt_module, "get_runtime_prompt", lambda key, fallback: fallback
    )
    prompt = build_system_prompt()
    assert prompt.count(PRESET_COMPONENTS_RULE_FRAGMENT) == 1
    assert prompt.count(KNOWN_TOOLS_RULE_FRAGMENT) == 1


def test_build_system_prompt_appends_preset_rules_to_db_override(monkeypatch):
    """生产 DB 定制 prompt 缺少规则时必须追加——幻觉工具问题正是线上 DB 覆盖场景。"""
    monkeypatch.setattr(
        system_prompt_module, "get_runtime_prompt", lambda key, fallback: "你是营销分析助手。"
    )
    prompt = build_system_prompt()
    assert "报告页预选组件路由规则" in prompt
    assert PRESET_COMPONENTS_RULE_FRAGMENT in prompt
    assert "工具白名单规则" in prompt
    assert KNOWN_TOOLS_RULE_FRAGMENT in prompt
