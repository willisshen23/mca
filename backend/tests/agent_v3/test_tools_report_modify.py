"""报告查看与修改工具测试（无 LLM/网络；指向 agent_v3 impl 层）。"""

import asyncio
import json
from types import SimpleNamespace

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import report_modify as rm

EN_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Marketing Campaign Analysis Report</title></head>
<body><h1>Marketing Campaign Analysis Report</h1><p>All content translated.</p></body>
</html>"""


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
    monkeypatch.setattr(rm, "validate_report_html", lambda html, **kw: _guard_valid())
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
    monkeypatch.setattr(rm, "validate_report_html", lambda html, **kw: _guard_valid())
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


def test_modify_report_translation_to_english_passes_guard(monkeypatch):
    """翻译场景：模型输出英文报告（英文标题）时应能通过展示校验。

    复现线上问题：标题关键词校验写死中文词（报告/分析/营销/活动），
    整篇翻译成英文后 missing_visible_report_title 必然失败。
    """
    state = {
        "html_report": "<html><body><h1>营销活动分析报告</h1><p>内容</p></body></html>",
        "report_context": {"report_id": "r-trans", "version": 1, "history": []},
    }

    class FakeModel:
        async def invoke(self, prompt):
            return SimpleNamespace(content=EN_HTML)

    # 不 mock validate_report_html，走真实校验逻辑
    monkeypatch.setattr(rm, "get_model", lambda role, **kw: FakeModel())
    monkeypatch.setattr(rm, "save_report_file", lambda rid, html, **kw: ("asset.html", 2))

    result = asyncio.run(
        rm.modify_report(
            _ctx(state=state),
            free_instruction="请把整份报告翻译成英文",
        )
    )
    payload = _json_content(result)
    assert payload["status"] == "ok"
    assert result.state_updates["html_report"].startswith("<!DOCTYPE html>")


def test_modify_report_english_title_without_translation_intent_still_rejected(monkeypatch):
    """非翻译指令下模型若意外输出英文标题，仍应被校验拦下。"""
    state = {
        "html_report": "<html><body><h1>营销活动分析报告</h1><p>内容</p></body></html>",
        "report_context": {"report_id": "r-guard", "version": 1, "history": []},
    }

    class FakeModel:
        async def invoke(self, prompt):
            return SimpleNamespace(content=EN_HTML)

    monkeypatch.setattr(rm, "get_model", lambda role, **kw: FakeModel())
    monkeypatch.setattr(rm, "save_report_file", lambda rid, html, **kw: ("asset.html", 2))

    content = asyncio.run(
        rm.modify_report(
            _ctx(state=state),
            content_changes=["把标题精简一下"],
        )
    )
    assert isinstance(content, str)
    assert "未通过展示校验" in content


def test_detect_translation_intent():
    assert rm._detect_translation("请把整份报告翻译成英文")
    assert rm._detect_translation("把报告翻译成日文")
    assert rm._detect_translation("translate the report to English")
    assert rm._detect_translation("把结论译为法语")
    assert not rm._detect_translation("把标题改成 Marketing Report")
    assert not rm._detect_translation("精简一下内容")
    assert not rm._detect_translation("")


def test_build_modify_prompt_translation_language_hint():
    prompt = rm._build_modify_prompt("<html></html>", "翻译成日文", {}, translation=True)
    assert "目标语言" in prompt
    assert "DOCTYPE" in prompt  # 结构要求仍保留
    default_prompt = rm._build_modify_prompt("<html></html>", "改标题", {})
    assert 'lang="zh-CN"' in default_prompt


def test_modify_report_translation_to_japanese_passes_guard(monkeypatch):
    """翻译成日文：任意语言标题也应能通过展示校验。"""
    ja_html = """<!DOCTYPE html>
<html lang="ja">
<head><meta charset="UTF-8"><title>マーケティングキャンペーンレポート</title></head>
<body><h1>マーケティングキャンペーンレポート</h1><p>翻訳された内容。</p></body>
</html>"""
    state = {
        "html_report": "<html><body><h1>营销活动分析报告</h1><p>内容</p></body></html>",
        "report_context": {"report_id": "r-ja", "version": 1, "history": []},
    }

    class FakeModel:
        async def invoke(self, prompt):
            return SimpleNamespace(content=ja_html)

    monkeypatch.setattr(rm, "get_model", lambda role, **kw: FakeModel())
    monkeypatch.setattr(rm, "save_report_file", lambda rid, html, **kw: ("asset.html", 2))

    result = asyncio.run(
        rm.modify_report(
            _ctx(state=state),
            free_instruction="请把整份报告翻译成日文",
        )
    )
    payload = _json_content(result)
    assert payload["status"] == "ok"
