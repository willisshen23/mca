"""与 backend/src/secrets.py 语义一致的 AES-256-GCM 静态加密
（ops 独立包，复制保持同步）。

ops 运行在 backend venv 内（cryptography 已提供），密文主密钥来源与
backend 相同：LLM_MASTER_KEY 环境变量 → LLM_MASTER_KEY_FILE → 调用方默认
路径（ops 默认取主应用 backend/data/secrets/master.key，因密文位于
backend/.env）。
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENC_PREFIX = "enc:v1:"
MASTER_KEY_ENV = "LLM_MASTER_KEY"
MASTER_KEY_FILE_ENV = "LLM_MASTER_KEY_FILE"

_NONCE_LEN = 12
_KEY_BYTES = 32


class MasterKeyMissingError(RuntimeError):
    """配置含密文但未找到主密钥。"""


def looks_encrypted(value: str) -> bool:
    return value.startswith(ENC_PREFIX)


def normalize_master_key(raw: str) -> bytes:
    text = raw.strip()
    if len(text) == _KEY_BYTES * 2 and all(c in "0123456789abcdefABCDEF" for c in text):
        return bytes.fromhex(text)
    try:
        key = base64.b64decode(text, validate=True)
    except Exception:
        key = b""
    if len(key) == _KEY_BYTES:
        return key
    raise ValueError(
        "主密钥必须是 32 字节（AES-256）：hex 64 字符或 base64 44 字符，"
        f"实际得到 {len(text)} 字符。"
    )


def load_master_key(
    environ: Mapping[str, str] | None = None,
    default_key_file: str | Path | None = None,
) -> bytes | None:
    environ = os.environ if environ is None else environ
    raw = environ.get(MASTER_KEY_ENV, "")
    if raw:
        return normalize_master_key(raw)
    file_path = environ.get(MASTER_KEY_FILE_ENV) or (
        str(default_key_file) if default_key_file is not None else ""
    )
    if file_path:
        path = Path(file_path)
        if path.is_file():
            return normalize_master_key(path.read_text(encoding="utf-8"))
    return None


def encrypt(plaintext: str, master_key: bytes) -> str:
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(master_key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return ENC_PREFIX + base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str, master_key: bytes) -> str:
    if not looks_encrypted(token):
        raise ValueError(f"非密文格式（缺少 {ENC_PREFIX} 前缀）: {token[:32]!r}...")
    try:
        payload = base64.b64decode(token[len(ENC_PREFIX):], validate=True)
    except Exception as exc:
        raise ValueError("密文 base64 解码失败，配置可能被截断或篡改") from exc
    if len(payload) <= _NONCE_LEN:
        raise ValueError("密文长度非法，配置可能被截断或篡改")
    nonce, ciphertext = payload[:_NONCE_LEN], payload[_NONCE_LEN:]
    try:
        plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ValueError(
            "密文解密失败：主密钥不匹配或密文被篡改（AES-GCM 校验未通过）"
        ) from exc
    return plaintext.decode("utf-8")


def maybe_decrypt(value: str, master_key: bytes | None) -> str:
    if not looks_encrypted(value):
        return value
    if master_key is None:
        raise MasterKeyMissingError(
            f"配置值以 {ENC_PREFIX} 开头（密文）但未找到主密钥。"
            f"请设置环境变量 {MASTER_KEY_ENV} 或 {MASTER_KEY_FILE_ENV}。"
        )
    return decrypt(value, master_key)


def generate_master_key() -> bytes:
    return os.urandom(_KEY_BYTES)
