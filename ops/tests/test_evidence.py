from __future__ import annotations

from src.collectors.base import Sample
from src.diagnosis.evidence import (
    build_evidence,
    estimate_tokens,
    mask_secrets,
    truncate_evidence,
)


def test_mask_secrets_masks_keys_and_passwords():
    text = '调用 http://gw/v1 使用 sk-abcdef1234567890，password="SuperSecret123"，正常内容保留'
    masked = mask_secrets(text)
    assert "SuperSecret123" not in masked
    assert "abcdef1234567890" not in masked
    assert "正常内容保留" in masked


def test_build_evidence_excludes_sensitive_config(settings):
    settings.llm_api_key = "sk-should-not-appear"
    settings.db_password = "db-pw"
    settings.bank_api_token = "bank-tok"
    settings.db_host = "10.0.0.1"
    check = {"id": "llm-latency", "title": "LLM 网关延迟", "level": "red", "message": "超时"}
    samples = {"logs": Sample("logs", True, metrics={"error_count": 3}, evidence=["line1"])}

    evidence = build_evidence(check, samples, settings)
    dumped = str(evidence)
    assert "sk-should-not-appear" not in dumped
    assert "db-pw" not in dumped
    assert "bank-tok" not in dumped
    assert evidence["app_config"]["db_host"] == "10.0.0.1"
    assert evidence["samples"]["logs"]["evidence"] == ["line1"]


def test_truncate_evidence_drops_oldest_snippets_first():
    evidence = {
        "check": {"id": "x"},
        "samples": {"logs": {"metrics": {}, "evidence": ["newest", "middle", "oldest" * 100]}},
        "app_config": {},
    }
    budget = estimate_tokens({"check": {"id": "x"}, "samples": {"logs": {"metrics": {}, "evidence": ["newest"]}}, "app_config": {}}) + 10

    out = truncate_evidence(evidence, budget)

    assert out["truncated"] is True
    remaining = out["samples"]["logs"]["evidence"]
    assert "newest" in remaining            # 最新优先保留
    assert estimate_tokens(out) <= budget


def test_estimate_tokens_scales_with_size():
    small = estimate_tokens({"a": "x" * 100})
    big = estimate_tokens({"a": "x" * 1000})
    assert big > small > 0
