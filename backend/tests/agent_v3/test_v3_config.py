"""agent_v3 配置项测试。

注意：openjiuwen 被 import 时（core.runner 链路）会以 override=True 把 cwd 的
.env 写入 os.environ——本测试必须 delenv 保证与环境/.env 内容无关。
"""

from src.config import Settings


def test_agent_v3_defaults(monkeypatch):
    monkeypatch.delenv("AGENT_V3_MAX_ITERATIONS", raising=False)
    s = Settings(_env_file=None)
    assert s.agent_v3_max_iterations == 50


def test_agent_v3_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_V3_MAX_ITERATIONS", "30")
    s = Settings(_env_file=None)
    assert s.agent_v3_max_iterations == 30
