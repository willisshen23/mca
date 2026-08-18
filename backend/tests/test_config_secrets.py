"""Settings 加载时对 enc:v1: 密文 API Key 的解密（fail-fast 语义）。"""
from __future__ import annotations

import pytest

from src.config import AGENT_NAMES, Settings, _API_KEY_FIELDS
from src.secrets import MasterKeyMissingError, encrypt, generate_master_key

KEY = generate_master_key()
KEY_HEX = KEY.hex()


def _settings(**env) -> Settings:
    # _env_file=None：不读 backend/.env，测试保持封闭
    return Settings(_env_file=None, **env)


def test_global_api_key_decrypted(monkeypatch):
    monkeypatch.setenv("LLM_MASTER_KEY", KEY_HEX)
    token = encrypt("sk-global", KEY)
    s = _settings(**{"LLM_API_KEY": token})
    assert s.llm_api_key == "sk-global"


def test_role_api_key_decrypted(monkeypatch):
    monkeypatch.setenv("LLM_MASTER_KEY", KEY_HEX)
    token = encrypt("sk-supervisor", KEY)
    s = _settings(**{"SUPERVISOR_LLM_API_KEY": token})
    assert s.supervisor_llm_api_key == "sk-supervisor"


def test_all_role_fields_covered():
    # 防止新增角色字段漏接解密 validator
    expected = {"llm_api_key"} | {f"{name}_llm_api_key" for name in AGENT_NAMES}
    assert set(_API_KEY_FIELDS) == expected


def test_plaintext_passthrough_without_master_key(monkeypatch):
    monkeypatch.delenv("LLM_MASTER_KEY", raising=False)
    monkeypatch.delenv("LLM_MASTER_KEY_FILE", raising=False)
    s = _settings(**{"LLM_API_KEY": "sk-plain"})
    assert s.llm_api_key == "sk-plain"


def test_ciphertext_without_master_key_fails_fast(monkeypatch):
    monkeypatch.delenv("LLM_MASTER_KEY", raising=False)
    monkeypatch.delenv("LLM_MASTER_KEY_FILE", raising=False)
    token = encrypt("sk-x", KEY)
    with pytest.raises(MasterKeyMissingError):
        _settings(**{"LLM_API_KEY": token})


def test_ciphertext_with_wrong_master_key_fails(monkeypatch):
    monkeypatch.setenv("LLM_MASTER_KEY", bytes.fromhex("22" * 32).hex())
    token = encrypt("sk-x", KEY)
    with pytest.raises(ValueError, match="解密失败"):
        _settings(**{"LLM_API_KEY": token})
