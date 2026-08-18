"""analysis_queue 工具测试（无网络，仅校验状态更新与校验逻辑；指向 agent_v3 impl 层）。"""

import asyncio
import json

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import analysis_queue as aq


def _ctx(state=None):
    return ToolContext(state=state or {}, request=ToolRequestContext(), tool_call_id="call-1")


def test_add_to_analysis_queue_success():
    state = {
        "activity_list": [
            {"activity_id": "act_001", "name": "五一优惠券促活", "channel": "短信"},
            {"activity_id": "act_002", "name": "中秋回馈", "channel": "外呼"},
        ]
    }
    result = asyncio.run(
        aq.add_to_analysis_queue(
            _ctx(state=state),
            activity_ids=["act_001", "act_003"],
            perspective="sms_analysis",
            metrics=["点击率"],
        )
    )

    queue = result.state_updates["analysis_queue"]
    assert len(queue) == 2
    assert queue[0]["activity_id"] == "act_001"
    assert queue[0]["verified"] is True
    assert queue[0]["config"]["perspective"] == "sms_analysis"
    assert queue[1]["activity_id"] == "act_003"
    assert queue[1]["verified"] is False

    payload = json.loads(result.content)
    assert payload["queue_length"] == 2
    assert payload["not_found"] == ["act_003"]


def test_add_to_analysis_queue_deduplicates():
    state = {
        "activity_list": [{"activity_id": "act_001", "name": "五一优惠券促活"}],
        "analysis_queue": [{"activity_id": "act_001", "name": "五一优惠券促活", "config": {}}],
    }
    result = asyncio.run(
        aq.add_to_analysis_queue(
            _ctx(state=state),
            activity_ids=["act_001"],
        )
    )
    queue = result.state_updates["analysis_queue"]
    assert len(queue) == 1
    payload = json.loads(result.content)
    assert payload["skipped"] == ["act_001"]


def test_add_to_analysis_queue_invalid_perspective():
    content = asyncio.run(
        aq.add_to_analysis_queue(
            _ctx(),
            activity_ids=["act_001"],
            perspective="not_exist",
        )
    )
    assert isinstance(content, str)
    assert content.startswith("ERROR:")
    assert "无效的分析视角" in content


def test_remove_from_analysis_queue():
    state = {
        "analysis_queue": [
            {"activity_id": "act_001", "name": "A"},
            {"activity_id": "act_002", "name": "B"},
        ]
    }
    result = asyncio.run(
        aq.remove_from_analysis_queue(
            _ctx(state=state),
            activity_ids=["act_001"],
        )
    )
    queue = result.state_updates["analysis_queue"]
    assert len(queue) == 1
    assert queue[0]["activity_id"] == "act_002"


def test_update_analysis_config():
    state = {
        "analysis_queue": [
            {"activity_id": "act_001", "name": "A", "config": {"perspective": ""}},
        ]
    }
    result = asyncio.run(
        aq.update_analysis_config(
            _ctx(state=state),
            activity_id="act_001",
            perspective="outbound_call_analysis",
            metrics=["接通率"],
            dimensions=["外呼时段"],
        )
    )
    queue = result.state_updates["analysis_queue"]
    assert queue[0]["config"]["perspective"] == "outbound_call_analysis"
    assert queue[0]["config"]["metrics"] == ["接通率"]


def test_update_analysis_config_not_found():
    content = asyncio.run(
        aq.update_analysis_config(
            _ctx(),
            activity_id="act_404",
        )
    )
    assert isinstance(content, str)
    assert content.startswith("ERROR:")


def test_update_analysis_config_omitted_fields_keep_existing():
    """省略 metrics/dimensions 时保持原值，不被清空。"""
    state = {
        "analysis_queue": [
            {
                "activity_id": "act_001",
                "name": "A",
                "config": {"metrics": ["点击率"], "dimensions": ["渠道"]},
            },
        ]
    }
    result = asyncio.run(
        aq.update_analysis_config(
            _ctx(state=state),
            activity_id="act_001",
            perspective="sms_analysis",
        )
    )
    config = result.state_updates["analysis_queue"][0]["config"]
    assert config["perspective"] == "sms_analysis"
    assert config["metrics"] == ["点击率"]
    assert config["dimensions"] == ["渠道"]
