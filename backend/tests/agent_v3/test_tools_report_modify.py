"""报告查看与修改工具测试（无 LLM/网络；指向 agent_v3 impl 层）。"""

import asyncio
import json
from types import SimpleNamespace

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import report_modify as rm


def _ctx(state=None):
    return ToolContext(state=state or {}, request=ToolRequestContext(), tool_call_id="call-1")


def _json_content(outcome):
    return json.loads(outcome.content)


def test_get_report_content_success():
    state = {
        "html_report": "<html><body><h1>报告</h1><p>内容</p></body></html>",
        "report_context": {"report_id": "r-1", "version": 1},
    }
    result = asyncio.run(
        rm.get_report_content(_ctx(state=state), summary_length=100)
    )
    payload = _json_content(result)
    assert payload["status"] == "ok"
    assert payload["version"] == 1
    assert "内容" in payload["text_summary"]


def test_get_report_content_no_report():
    content = asyncio.run(
        rm.get_report_content(_ctx())
    )
    assert isinstance(content, str)
    assert content.startswith("ERROR:")


def test_modify_report_success(monkeypatch):
    state = {
        "html_report": "<html><body><h1>原报告</h1></body></html>",
        "report_context": {"report_id": "r-1", "version": 1, "history": []},
    }

    class FakeModel:
        async def invoke(self, prompt):
            return SimpleNamespace(
                content="<html><body><h1>修改后报告</h1></body></html>"
            )

    def _guard_valid():
        return SimpleNamespace(
            valid=True,
            issues=[],
            to_dict=lambda *, retry_count, max_retries: {
                "valid": True,
                "retry_count": retry_count,
                "max_retries": max_retries,
            },
        )

    monkeypatch.setattr(rm, "get_model", lambda role, **kw: FakeModel())
    monkeypatch.setattr(rm, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rm, "save_report_file", lambda rid, html, **kw: ("asset.html", 2))

    result = asyncio.run(
        rm.modify_report(
            _ctx(state=state),
            content_changes=["标题改为修改后报告"],
        )
    )
    payload = _json_content(result)
    assert payload["status"] == "ok"
    assert payload["version"] == 2
    assert "<h1>修改后报告</h1>" in result.state_updates["html_report"]
    assert len(result.state_updates["report_context"]["history"]) == 1


def test_modify_report_no_instruction():
    state = {
        "html_report": "<html><body><h1>报告</h1></body></html>",
        "report_context": {},
    }
    content = asyncio.run(
        rm.modify_report(_ctx(state=state))
    )
    assert isinstance(content, str)
    assert "缺少修改指令" in content


def test_modify_report_append_activity(monkeypatch):
    """增量修改：把新活动追加到现有报告中，应复用原报告结构。"""
    state = {
        "html_report": "<html><body><h1>活动分析报告</h1><ul><li>活动 A</li></ul></body></html>",
        "report_context": {"report_id": "r-append", "version": 1, "history": []},
    }

    class FakeModel:
        async def invoke(self, prompt):
            # 验证 prompt 里确实包含增量修改指令
            assert "追加" in prompt or "添加" in prompt
            return SimpleNamespace(
                content="<html><body><h1>活动分析报告</h1><ul><li>活动 A</li><li>活动 B（新增）</li></ul></body></html>"
            )

    def _guard_valid():
        return SimpleNamespace(
            valid=True,
            issues=[],
            to_dict=lambda *, retry_count, max_retries: {
                "valid": True,
                "retry_count": retry_count,
                "max_retries": max_retries,
            },
        )

    monkeypatch.setattr(rm, "get_model", lambda role, **kw: FakeModel())
    monkeypatch.setattr(rm, "validate_report_html", lambda html: _guard_valid())
    monkeypatch.setattr(rm, "save_report_file", lambda rid, html, **kw: ("asset.html", 2))

    result = asyncio.run(
        rm.modify_report(
            _ctx(state=state),
            content_changes=["把活动 B 追加到对比列表中"],
        )
    )
    payload = _json_content(result)
    assert payload["status"] == "ok"
    assert payload["version"] == 2
    assert "活动 B（新增）" in result.state_updates["html_report"]
    assert "活动 A" in result.state_updates["html_report"]
