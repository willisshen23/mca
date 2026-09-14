"""审批话术生成单元测试：假模型，不起 agent、不走网络。"""

from types import SimpleNamespace

import pytest

from src.agent_v3 import approval_wording


def _fake_model(content):
    async def invoke(_prompt):
        return SimpleNamespace(content=content)

    return SimpleNamespace(invoke=invoke)


async def test_wording_returns_cleaned_text(monkeypatch):
    monkeypatch.setattr(approval_wording, "get_model",
                        lambda _role: _fake_model(' "我将把活动X加入报告并覆盖当前报告。" \n'))
    text = await approval_wording.generate_approval_wording(
        tool_display="生成分析报告", activity_names=["活动X"], overwrite=True)
    assert text == "我将把活动X加入报告并覆盖当前报告。"


async def test_wording_empty_on_model_failure(monkeypatch):
    def _bad_model(_role):
        async def invoke(_prompt):
            raise RuntimeError("超时")
        return SimpleNamespace(invoke=invoke)

    monkeypatch.setattr(approval_wording, "get_model", _bad_model)
    text = await approval_wording.generate_approval_wording(tool_display="修改报告")
    assert text == ""


async def test_wording_rejects_overlong_output(monkeypatch):
    monkeypatch.setattr(approval_wording, "get_model",
                        lambda _role: _fake_model("长" * 200))
    text = await approval_wording.generate_approval_wording(tool_display="修改报告")
    assert text == ""


async def test_wording_rejects_empty_output(monkeypatch):
    monkeypatch.setattr(approval_wording, "get_model", lambda _role: _fake_model("  "))
    text = await approval_wording.generate_approval_wording(tool_display="修改报告")
    assert text == ""
