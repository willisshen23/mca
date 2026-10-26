"""agent_v3 配置项测试。

注意：openjiuwen 被 import 时（core.runner 链路）会以 override=True 把 cwd 的
.env 写入 os.environ——本测试必须 delenv 保证与环境/.env 内容无关。
"""

import pytest

from src.config import Settings


def test_agent_v3_defaults(monkeypatch):
    monkeypatch.delenv("AGENT_V3_MAX_ITERATIONS", raising=False)
    for name, field in Settings.model_fields.items():
        if name.startswith("agent_v3_context_"):
            monkeypatch.delenv(field.alias, raising=False)
    s = Settings(_env_file=None)
    assert s.agent_v3_max_iterations == 50
    assert s.agent_v3_context_compression_enabled is True
    assert s.agent_v3_context_compression_tokens_threshold == 120000
    assert s.agent_v3_context_offload_enabled is True
    assert s.agent_v3_context_reload_enabled is True
    assert s.agent_v3_context_workspace_dir == "data/agent_workspace"
    assert s.agent_v3_context_window_rounds == 20


def test_agent_v3_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_V3_MAX_ITERATIONS", "30")
    monkeypatch.setenv("AGENT_V3_CONTEXT_COMPRESSION_ENABLED", "false")
    monkeypatch.setenv("AGENT_V3_CONTEXT_RELOAD_ENABLED", "false")
    monkeypatch.setenv("AGENT_V3_CONTEXT_WINDOW_ROUNDS", "0")
    s = Settings(_env_file=None)
    assert s.agent_v3_max_iterations == 30
    assert s.agent_v3_context_compression_enabled is False
    assert s.agent_v3_context_reload_enabled is False
    assert s.agent_v3_context_window_rounds == 0


def test_agent_v3_context_rejects_invalid_values(monkeypatch):
    monkeypatch.setenv("AGENT_V3_CONTEXT_COMPRESSION_TOKENS_THRESHOLD", "0")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
