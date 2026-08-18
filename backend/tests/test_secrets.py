"""src/secrets AES-256-GCM 静态加密单测。"""
from __future__ import annotations

import base64

import pytest

from src.secrets import (
    ENC_PREFIX,
    MasterKeyMissingError,
    decrypt,
    encrypt,
    generate_master_key,
    load_master_key,
    looks_encrypted,
    maybe_decrypt,
    normalize_master_key,
)

KEY = bytes.fromhex("00" * 32)  # 固定测试密钥（仅测试用）


def test_roundtrip():
    token = encrypt("sk-abc123", KEY)
    assert token.startswith(ENC_PREFIX)
    assert decrypt(token, KEY) == "sk-abc123"


def test_same_plaintext_different_ciphertext():
    assert encrypt("sk-abc123", KEY) != encrypt("sk-abc123", KEY)


def test_tamper_detected():
    token = encrypt("sk-abc123", KEY)
    corrupted = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
    with pytest.raises(ValueError, match="解密失败"):
        decrypt(corrupted, KEY)


def test_wrong_key_rejected():
    token = encrypt("sk-abc123", KEY)
    with pytest.raises(ValueError, match="解密失败"):
        decrypt(token, bytes.fromhex("11" * 32))


def test_looks_encrypted():
    assert looks_encrypted(ENC_PREFIX + "x")
    assert not looks_encrypted("sk-plain")
    assert not looks_encrypted("")


def test_decrypt_rejects_non_ciphertext():
    with pytest.raises(ValueError, match="非密文格式"):
        decrypt("sk-plain", KEY)


def test_maybe_decrypt_passthrough_plaintext():
    assert maybe_decrypt("sk-plain", None) == "sk-plain"
    assert maybe_decrypt("", None) == ""


def test_maybe_decrypt_missing_key_raises():
    token = encrypt("sk-abc123", KEY)
    with pytest.raises(MasterKeyMissingError):
        maybe_decrypt(token, None)


def test_normalize_hex_and_base64():
    key = generate_master_key()
    assert normalize_master_key(key.hex()) == key
    assert normalize_master_key(base64.b64encode(key).decode()) == key
    assert normalize_master_key(f"  {key.hex()}\n") == key  # 容忍首尾空白


def test_normalize_rejects_bad_length():
    with pytest.raises(ValueError, match="32 字节"):
        normalize_master_key("tooshort")


def test_load_master_key_from_env(monkeypatch):
    key = generate_master_key()
    monkeypatch.setenv("LLM_MASTER_KEY", key.hex())
    assert load_master_key() == key


def test_load_master_key_from_file(tmp_path, monkeypatch):
    key = generate_master_key()
    key_file = tmp_path / "master.key"
    key_file.write_text(base64.b64encode(key).decode() + "\n", encoding="utf-8")
    monkeypatch.delenv("LLM_MASTER_KEY", raising=False)
    monkeypatch.delenv("LLM_MASTER_KEY_FILE", raising=False)
    assert load_master_key(default_key_file=key_file) == key


def test_env_priority_over_file(tmp_path, monkeypatch):
    key_env = generate_master_key()
    key_file = generate_master_key()
    key_path = tmp_path / "master.key"
    key_path.write_text(key_file.hex() + "\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MASTER_KEY", key_env.hex())
    monkeypatch.delenv("LLM_MASTER_KEY_FILE", raising=False)
    assert load_master_key(default_key_file=key_path) == key_env


def test_load_master_key_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("LLM_MASTER_KEY", raising=False)
    monkeypatch.delenv("LLM_MASTER_KEY_FILE", raising=False)
    assert load_master_key() is None
