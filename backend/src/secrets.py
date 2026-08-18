"""LLM API Key 等敏感配置的 AES-256-GCM 静态加密（密文存 .env，主密钥分离）。

密文格式：``enc:v1:<base64(nonce ‖ ciphertext ‖ tag)>``

- 配置值以 ``enc:v1:`` 开头视为密文，否则原样透传（向后兼容明文配置）；
- 主密钥为 32 字节（AES-256），来源按优先级：
  1. 环境变量 ``LLM_MASTER_KEY``（hex 64 字符或 base64 44 字符）；
  2. 环境变量 ``LLM_MASTER_KEY_FILE`` 指向的密钥文件；
  3. 调用方传入的默认密钥文件路径
     （backend 为 ``backend/data/secrets/master.key``）。
- 密文存在但主密钥缺失 → 抛 ``MasterKeyMissingError``（启动 fail-fast，
  避免把密文当明文发给上游；纯明文配置不受影响）。

密钥生成/配置加密工具：``python scripts/env_secret.py``（见该文件 docstring）。
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

_NONCE_LEN = 12  # AES-GCM 推荐 nonce 长度
_KEY_BYTES = 32  # AES-256


class MasterKeyMissingError(RuntimeError):
    """配置含密文但未找到主密钥。"""


def looks_encrypted(value: str) -> bool:
    """判断配置值是否为 enc:v1: 密文。"""
    return value.startswith(ENC_PREFIX)


def normalize_master_key(raw: str) -> bytes:
    """把主密钥文本（hex 64 字符 / base64 44 字符）规整为 32 字节。

    密钥来自密钥文件时可能带换行/空白，先 strip。
    """
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
        f"实际得到 {len(text)} 字符。可用 scripts/env_secret.py init 生成。"
    )


def load_master_key(
    environ: Mapping[str, str] | None = None,
    default_key_file: str | Path | None = None,
) -> bytes | None:
    """按优先级读取主密钥；未配置任何来源时返回 None（纯明文配置）。

    顺序：``LLM_MASTER_KEY`` 环境变量 → ``LLM_MASTER_KEY_FILE`` 指定文件 →
    ``default_key_file`` 默认路径（调用方传入，如 backend/data/secrets/master.key）。
    """
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
    """AES-256-GCM 加密，返回 ``enc:v1:`` 密文字符串（每次随机 nonce）。"""
    nonce = os.urandom(_NONCE_LEN)
    ciphertext = AESGCM(master_key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return ENC_PREFIX + base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str, master_key: bytes) -> str:
    """解密 ``enc:v1:`` 密文；密文被篡改或密钥错误时抛异常。"""
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
    """密文解密、明文透传；密文缺主密钥时抛 MasterKeyMissingError。"""
    if not looks_encrypted(value):
        return value
    if master_key is None:
        raise MasterKeyMissingError(
            f"配置值以 {ENC_PREFIX} 开头（密文）但未找到主密钥。"
            f"请设置环境变量 {MASTER_KEY_ENV} 或 {MASTER_KEY_FILE_ENV}"
            f"（未指定文件时回退 backend/data/secrets/master.key）。"
        )
    return decrypt(value, master_key)


def generate_master_key() -> bytes:
    """生成新的 32 字节主密钥。"""
    return os.urandom(_KEY_BYTES)
