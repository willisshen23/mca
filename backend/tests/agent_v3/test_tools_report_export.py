"""export_report 工具测试（指向 agent_v3 impl 层）。

注意：test_export_pdf_success / test_export_unsupported_format 为 M3 既有失败
（M3 起仅支持 HTML 导出，测试未同步），转换后须保持原失败签名不变，不趁机修。
"""

import asyncio
import json

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import report_export as rexp


def _ctx(state=None, **req):
    return ToolContext(
        state=state or {},
        request=ToolRequestContext(**req),
        tool_call_id="call-1",
    )


def _json_content(outcome):
    return json.loads(outcome.content)


def test_export_pdf_success(monkeypatch, tmp_path):
    state = {
        "html_report": "<html><body><h1>报告</h1></body></html>",
        "report_context": {"report_id": "r-1"},
    }
    monkeypatch.setattr(
        rexp, "convert_report_html_to_pdf", lambda html, path: path
    )

    result = asyncio.run(
        rexp.export_report(_ctx(state=state), format="pdf")
    )
    payload = _json_content(result)
    assert payload["status"] == "ok"
    assert payload["format"] == "pdf"
    assert result.state_updates["formatted_output_path"].endswith(".pdf")


def test_export_unsupported_format():
    state = {"html_report": "<html></html>", "report_context": {}}
    content = asyncio.run(
        rexp.export_report(_ctx(state=state), format="docx")
    )
    assert isinstance(content, str)
    assert "当前仅支持导出 PDF 或 HTML，不支持 DOCX" in content


def test_export_no_report():
    content = asyncio.run(
        rexp.export_report(_ctx())
    )
    assert isinstance(content, str)
    assert content.startswith("ERROR:")


def test_export_falls_back_to_request_context_request_id(monkeypatch, tmp_path):
    """Task8 修复回归：report_context 缺 report_id 时，文件名回退到
    ctx.request.request_id（turn 级键不再由壳层注入 state 快照）。"""
    state = {
        "html_report": "<html><body><h1>报告</h1></body></html>",
        "report_context": {},
    }

    class _Settings:
        report_export_dir = str(tmp_path)

    monkeypatch.setattr(rexp, "get_settings", lambda: _Settings())
    monkeypatch.setattr(rexp, "write_report_html", lambda html, path: path)

    result = asyncio.run(
        rexp.export_report(_ctx(state=state, request_id="req-turn-9"), format="html")
    )
    payload = _json_content(result)
    assert payload["status"] == "ok"
    assert payload["file_name"] == "report-req-turn-9.html"
    assert result.state_updates["formatted_output_path"].endswith("report-req-turn-9.html")
