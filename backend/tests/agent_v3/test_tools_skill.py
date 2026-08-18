"""get_available_skills 工具测试（mock 服务层，无网络/DB；指向 agent_v3 impl 层）。"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext
from src.agent_v3.tools.impl import skill as skill_tool


def _ctx():
    return ToolContext(state={}, request=ToolRequestContext(), tool_call_id="call-1")


def test_get_available_skills_success(monkeypatch):
    skills = [
        {"id": 1, "code": "s1", "name": "转化漏斗分析", "cat": "活动分析", "desc": "分析转化漏斗", "version": "v1", "useCnt": 3},
        {"id": 2, "code": "s2", "name": "渠道效果对比", "cat": "活动分析", "desc": "对比渠道效果", "version": "v1", "useCnt": 1},
    ]
    monkeypatch.setattr(skill_tool, "_list_agent_skills", lambda category="", keyword="": skills)

    content = asyncio.run(skill_tool.get_available_skills(_ctx()))

    payload = json.loads(content)
    assert payload["count"] == 2
    assert payload["skills"][0]["name"] == "转化漏斗分析"
    assert payload["skills"][0]["category"] == "活动分析"


def test_get_available_skills_empty_result(monkeypatch):
    monkeypatch.setattr(skill_tool, "_list_agent_skills", lambda category="", keyword="": [])

    content = asyncio.run(skill_tool.get_available_skills(_ctx(), keyword="不存在"))

    assert content.startswith("ERROR:")
    assert "未查询到" in content


def test_get_available_skills_exception_returns_error(monkeypatch):
    def _raise(category="", keyword=""):
        raise RuntimeError("db down")

    monkeypatch.setattr(skill_tool, "_list_agent_skills", _raise)

    content = asyncio.run(skill_tool.get_available_skills(_ctx()))

    assert content.startswith("ERROR:")
    assert "db down" in content


def test_list_agent_skills_filters_by_category(monkeypatch):
    class _FakeCategory:
        def __init__(self, name):
            self.name = name

    class _FakeSkill:
        def __init__(self, name, cat):
            self.id = 1
            self.code = "c"
            self.name = name
            self.category = _FakeCategory(cat)
            self.category_id = 1
            self.description = ""
            self.template = "tpl"
            self.status = "active"
            self.version = "v1"
            self.use_count = 0

    monkeypatch.setattr(
        skill_tool,
        "list_skills",
        lambda db, keyword="": [_FakeSkill("转化漏斗分析", "活动分析"), _FakeSkill("客群画像", "客户洞察")],
    )
    monkeypatch.setattr(skill_tool, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))

    result = skill_tool._list_agent_skills(category="客户洞察")

    assert len(result) == 1
    assert result[0]["name"] == "客群画像"
