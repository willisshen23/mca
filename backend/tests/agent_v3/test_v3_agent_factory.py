"""agent_v3 agent_factory 测试：monkeypatch 重对象，验证组装契约。"""

import asyncio
from types import SimpleNamespace

import pytest

from src.agent_v3 import agent_factory
from src.agent_v3.tools import ALL_V3_TOOLS
from src.config import Settings


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
    assert client_cfg.use_shared_llm_http_client is False
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
    settings = Settings(
        _env_file=None,
        LLM_API_KEY="k",
        LLM_BASE_URL="https://x",
        LLM_MODEL="m",
        AGENT_V3_CONTEXT_COMPRESSION_ENABLED=True,
        AGENT_V3_CONTEXT_WINDOW_ROUNDS=20,
    )
    monkeypatch.setattr(agent_factory, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_factory, "build_system_prompt", lambda: "sys")
    agent = await agent_factory.get_v3_agent()
    assert agent is not None
    assert [name for name, _ in agent._config.context_processors] == [
        "MessageOffloader", "DialogueCompressor",
    ]
    assert agent._config.context_engine_config.default_window_round_num == 20
    assert agent._config.context_engine_config.enable_reload is True
    assert agent._config.sys_operation_id == "agent-v3-context-offload"
    assert str(agent._config.workspace.root_path).endswith("data/agent_workspace")
    assert agent.ability_manager.get("read_file") is not None
    assert "OFFLOAD marker" in agent.prompt_builder.build()
    # 单例
    again = await agent_factory.get_v3_agent()
    assert again is agent


def test_build_v3_context_configs_honors_switches():
    settings = Settings(
        _env_file=None,
        AGENT_V3_CONTEXT_COMPRESSION_ENABLED=False,
        AGENT_V3_CONTEXT_OFFLOAD_ENABLED=False,
        AGENT_V3_CONTEXT_RELOAD_ENABLED=False,
        AGENT_V3_CONTEXT_WINDOW_ROUNDS=0,
    )
    client_cfg, request_cfg = agent_factory.build_v3_model_configs(settings)
    engine_cfg, processors = agent_factory.build_v3_context_configs(
        settings, client_cfg, request_cfg,
    )
    assert processors == []
    assert engine_cfg.default_window_round_num is None
    assert engine_cfg.enable_reload is False
    assert engine_cfg.context_window_tokens == 262144
    assert agent_factory.build_v3_reload_config(settings) == (None, None)


def test_build_v3_context_configs_rejects_invalid_trim_size():
    settings = Settings(
        _env_file=None,
        AGENT_V3_CONTEXT_OFFLOAD_LARGE_MESSAGE_THRESHOLD=100,
        AGENT_V3_CONTEXT_OFFLOAD_TRIM_SIZE=100,
    )
    client_cfg, request_cfg = agent_factory.build_v3_model_configs(settings)
    with pytest.raises(ValueError, match="TRIM_SIZE"):
        agent_factory.build_v3_context_configs(settings, client_cfg, request_cfg)


def test_build_v3_context_configs_rejects_reload_without_offload():
    settings = Settings(_env_file=None, AGENT_V3_CONTEXT_OFFLOAD_ENABLED=False)
    client_cfg, request_cfg = agent_factory.build_v3_model_configs(settings)
    with pytest.raises(ValueError, match="要求同时启用"):
        agent_factory.build_v3_context_configs(settings, client_cfg, request_cfg)
