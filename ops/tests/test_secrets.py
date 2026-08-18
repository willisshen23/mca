"""ops 侧：backend/.env 中密文 LLM_API_KEY 的解密加载（与 src/secrets.py 配套）。"""
from __future__ import annotations

import pytest

from src.config import load_settings
from src.secrets import MasterKeyMissingError, encrypt, generate_master_key

KEY = generate_master_key()
KEY_HEX = KEY.hex()


def _write_main_env(main_app, llm_value: str) -> None:
    (main_app / ".env").write_text(
        f"LLM_API_KEY={llm_value}\n"
        "LLM_BASE_URL=http://gw:4000/v1\n"
        "LLM_MODEL=deepseek\n",
        encoding="utf-8",
    )


def test_ops_decrypts_encrypted_backend_env(tmp_path):
    main_app = tmp_path / "backend"
    main_app.mkdir()
    _write_main_env(main_app, encrypt("sk-secret", KEY))
    env_file = tmp_path / "ops.env"
    env_file.write_text(f"OPS_MAIN_APP_DIR={main_app}\n", encoding="utf-8")

    s = load_settings(env_file=env_file, environ={"LLM_MASTER_KEY": KEY_HEX})

    assert s.llm_api_key == "sk-secret"


def test_ops_plaintext_passthrough(tmp_path):
    main_app = tmp_path / "backend"
    main_app.mkdir()
    _write_main_env(main_app, "sk-plain")
    env_file = tmp_path / "ops.env"
    env_file.write_text(f"OPS_MAIN_APP_DIR={main_app}\n", encoding="utf-8")

    s = load_settings(env_file=env_file, environ={})

    assert s.llm_api_key == "sk-plain"


def test_ops_ciphertext_without_master_key_fails(tmp_path):
    main_app = tmp_path / "backend"
    main_app.mkdir()
    _write_main_env(main_app, encrypt("sk-secret", KEY))
    env_file = tmp_path / "ops.env"
    env_file.write_text(f"OPS_MAIN_APP_DIR={main_app}\n", encoding="utf-8")

    with pytest.raises(MasterKeyMissingError):
        load_settings(env_file=env_file, environ={})
