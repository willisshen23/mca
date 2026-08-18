"""parse_uploaded_data 工具测试（指向 agent_v3 impl 层）。"""

import asyncio
import json

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import data_parse as dp


def _ctx(state=None, **req):
    defaults = {"uploaded_file_path": "/tmp/test.xlsx"}
    defaults.update(req)
    return ToolContext(state=state or {}, request=ToolRequestContext(**defaults), tool_call_id="call-1")


def test_parse_uploaded_data_success(monkeypatch):
    captured: dict = {}

    def fake_node(state):
        captured.update(state)
        return {
            "uploaded_activity_dataset": {
                "file_name": "test.xlsx",
                "total_rows": 3,
                "activities": [
                    {"activity_id": "u-1", "name": "上传活动1"},
                ],
            },
            "activity_list": [{"activity_id": "u-1", "name": "上传活动1"}],
            "next_agent": "supervisor",
        }

    monkeypatch.setattr(dp, "activity_file_parse_node", fake_node)
    monkeypatch.setattr(dp, "summarize_uploaded_file", lambda path: "{}")

    result = asyncio.run(dp.parse_uploaded_data(_ctx(request_id="req-turn-7"), confirm=True))
    payload = json.loads(result.content)
    assert payload["status"] == "ok"
    assert payload["activities"] == 1
    assert result.state_updates["activity_list"][0]["activity_id"] == "u-1"
    # Task8 修复回归：seed 的 request_id 来自 ToolContext.request（turn 级键不再注入 state）
    assert captured["request_id"] == "req-turn-7"
    assert captured["uploaded_file_path"] == "/tmp/test.xlsx"


def test_parse_uploaded_data_no_file():
    content = asyncio.run(dp.parse_uploaded_data(_ctx(uploaded_file_path=""), confirm=True))
    assert isinstance(content, str)
    assert content.startswith("ERROR:")


def test_parse_uploaded_data_already_parsed():
    state = {
        "uploaded_activity_dataset": {
            "file_name": "test.xlsx",
            "activities": [{"activity_id": "u-1", "name": "A"}],
        }
    }
    result = asyncio.run(dp.parse_uploaded_data(_ctx(state=state), confirm=True))
    assert isinstance(result, str)
    assert "已解析" in result
