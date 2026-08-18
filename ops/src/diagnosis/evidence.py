from __future__ import annotations

import json
import re

_SK_RE = re.compile(r"\bsk-[A-Za-z0-9]{4}[A-Za-z0-9_-]*")
_KV_RE = re.compile(
    r'("(?:[^"]*(?:key|token|password|secret|passwd)[^"]*)"\s*:\s*")[^"]*(")', re.I
)
_PLAIN_KV_RE = re.compile(
    r"\b(password|passwd|token|secret|api[_-]?key)\b\s*[=:]\s*['\"]?[^\s'\"]+",
    re.I,
)

_CHARS_PER_TOKEN = 2  # 中英文混合的保守估算


def mask_secrets(text: str) -> str:
    text = _SK_RE.sub("sk-****", text)
    text = _KV_RE.sub(r"\1****\2", text)
    return _PLAIN_KV_RE.sub(lambda m: f"{m.group(1)}=****", text)


def build_evidence(check: dict, samples: dict, settings) -> dict:
    """组装证据包。app_config 只挑非敏感字段，密钥从字段层面就不进入。"""
    evidence = {
        "check": check,
        "samples": {
            name: {"metrics": s.metrics, "evidence": list(s.evidence)}
            for name, s in samples.items()
        },
        "app_config": {
            "llm_base_url": settings.llm_base_url,
            "llm_model": settings.llm_model,
            "llm_timeout_s": settings.llm_timeout_s,
            "db_host": settings.db_host,
            "db_port": settings.db_port,
            "db_name": settings.db_name,
            "bank_api_urls": settings.bank_api_urls,
        },
    }
    # 兜底：序列化后整体脱敏再反序列化，防止 metrics/日志片段里带出密钥
    masked = mask_secrets(json.dumps(evidence, ensure_ascii=False))
    return json.loads(masked)


def estimate_tokens(evidence: dict) -> int:
    return len(json.dumps(evidence, ensure_ascii=False)) // _CHARS_PER_TOKEN


def truncate_evidence(evidence: dict, budget_tokens: int) -> dict:
    """超预算时按"最新错误优先"丢弃片段（evidence 列表新的在前，从尾部丢）。"""
    evidence = json.loads(json.dumps(evidence, ensure_ascii=False))  # 深拷贝
    evidence["truncated"] = False  # 提前占位，让循环内的估算包含该字段的开销
    while estimate_tokens(evidence) > budget_tokens:
        longest_name, longest_len = None, 0
        for name, section in evidence.get("samples", {}).items():
            length = len(section.get("evidence") or [])
            if length > longest_len:
                longest_name, longest_len = name, length
        if longest_name is None:
            break  # 没有可丢的片段了
        evidence["samples"][longest_name]["evidence"].pop()  # 丢最旧的一条
        evidence["truncated"] = True
    return evidence
