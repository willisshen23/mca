"""P3 终审 C1/M1 回归：管线 _latest_user_text 须兼容 v3 纯 dict 消息 seed。

v3 report_gen seed 用 {"role": "user", "content": ...} dict 替代旧框架消息对象，
修复前 messages[-1].content 会抛 AttributeError，默认报告生成直接崩溃。
"""
from __future__ import annotations

from src.report_pipeline.capabilities import marketing_report_synthesis, template_matching


class _FakeMessage:
    """模拟旧框架消息对象（仅 content 属性）。"""

    def __init__(self, content: str):
        self.content = content


def test_template_matching_latest_user_text_dict_message():
    state = {"messages": [{"role": "user", "content": "  帮我生成营销活动报告  "}]}
    assert template_matching._latest_user_text(state) == "帮我生成营销活动报告"


def test_template_matching_latest_user_text_object_fallback():
    state = {"messages": [_FakeMessage("旧对象消息")]}
    assert template_matching._latest_user_text(state) == "旧对象消息"


def test_template_matching_latest_user_text_empty():
    assert template_matching._latest_user_text({"messages": []}) == ""
    assert template_matching._latest_user_text({}) == ""


def test_synthesis_latest_user_text_dict_message():
    state = {"messages": [{"role": "user", "content": "  汇总这个活动  "}]}
    assert marketing_report_synthesis._latest_user_text(state) == "汇总这个活动"


def test_synthesis_latest_user_text_object_fallback():
    state = {"messages": [_FakeMessage("旧对象消息")]}
    assert marketing_report_synthesis._latest_user_text(state) == "旧对象消息"


def test_synthesis_report_user_text_dict_message_fallback():
    """original_user_text 缺省时回退到 dict 消息的 content。"""
    state = {"messages": [{"role": "user", "content": "dict 消息指令"}]}
    assert marketing_report_synthesis._report_user_text(state) == "dict 消息指令"


def test_synthesis_report_user_text_original_wins():
    state = {
        "original_user_text": "原始指令",
        "messages": [{"role": "user", "content": "dict 消息指令"}],
    }
    assert marketing_report_synthesis._report_user_text(state) == "原始指令"
