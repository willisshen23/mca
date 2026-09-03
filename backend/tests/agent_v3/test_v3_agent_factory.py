"""agent_v3 agent_factory 测试：monkeypatch 重对象，验证组装契约。"""

import asyncio
from types import SimpleNamespace

import pytest

from src.agent_v3 import agent_factory
from src.agent_v3.tools import ALL_V3_TOOLS


def setup_function():
    agent_factory._agent = None


def test_build_model_config_prefers_main_role(monkeypatch):
    settings = SimpleNamespace(
        agent_v2_main_llm_api_key="k1", agent_v2_main_llm_base_url="https://main",
        agent_v2_main_llm_model="m1",
        llm_api_key="gk", llm_base_url="https://global", llm_model="gm",
        llm_verify_ssl=False,
        llm_max_retries=1,
    )
    client_cfg, request_cfg = agent_factory.build_v3_model_configs(settings)
    assert client_cfg.api_key == "k1"
    assert client_cfg.api_base == "https://main"
    assert client_cfg.max_retries == 1  # SDK 默认 3 会把 429 限流放大，必须显式压低
    assert request_cfg.model_name == "m1"


def test_build_model_config_falls_back_to_global(monkeypatch):
    settings = SimpleNamespace(
        agent_v2_main_llm_api_key="", agent_v2_main_llm_base_url="",
        agent_v2_main_llm_model="",
        llm_api_key="gk", llm_base_url="https://global", llm_model="gm",
        llm_verify_ssl=False,
        llm_max_retries=1,
    )
    client_cfg, request_cfg = agent_factory.build_v3_model_configs(settings)
    assert client_cfg.api_key == "gk"
    assert request_cfg.model_name == "gm"


async def test_get_v3_agent_registers_tools_and_rails(monkeypatch):
    settings = SimpleNamespace(
        agent_v2_main_llm_api_key="", agent_v2_main_llm_base_url="",
        agent_v2_main_llm_model="",
        llm_api_key="k", llm_base_url="https://x", llm_model="m",
        llm_verify_ssl=False,
        llm_max_retries=1,
        agent_v3_max_iterations=50,
        agent_v3_max_tool_calls_per_run=8,
    )
    monkeypatch.setattr(agent_factory, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_factory, "build_system_prompt", lambda: "sys")
    agent = await agent_factory.get_v3_agent()
    assert agent is not None
    # 单例
    again = await agent_factory.get_v3_agent()
    assert again is agent
