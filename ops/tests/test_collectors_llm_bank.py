from __future__ import annotations

import asyncio

import httpx

from src.collectors import COLLECTORS, bank_api, llm_gateway


def _settings_with_llm(settings):
    settings.llm_base_url = "http://gw:4000/v1"
    settings.llm_api_key = "sk-x"
    settings.llm_model = "deepseek"
    return settings


def test_llm_gateway_ok(settings):
    _settings_with_llm(settings)

    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer sk-x"
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
        })

    sample = asyncio.run(llm_gateway._probe(settings, transport=httpx.MockTransport(handler)))

    assert sample.metrics["reachable"] is True
    assert sample.metrics["latency_s"] is not None


def test_llm_gateway_down(settings):
    _settings_with_llm(settings)

    def handler(request):
        raise httpx.ConnectError("refused")

    sample = asyncio.run(llm_gateway._probe(settings, transport=httpx.MockTransport(handler)))

    assert sample.metrics["reachable"] is False
    assert "refused" in sample.metrics["error"]


def test_llm_gateway_unconfigured(settings):
    sample = asyncio.run(llm_gateway.collect(settings))

    assert sample.metrics["configured"] is False
    assert sample.metrics["reachable"] is False


def test_bank_api_mixed(settings):
    settings.bank_api_urls = ["http://bank/a", "http://bank/b"]
    settings.bank_api_token = "tok"

    def handler(request):
        assert request.headers["Authorization"] == "Bearer tok"
        if request.url.path == "/a":
            return httpx.Response(200, json={})
        raise httpx.ConnectError("refused")

    transport = httpx.MockTransport(handler)
    sample = asyncio.run(bank_api._probe_all(settings, transport=transport))

    eps = sample.metrics["endpoints"]
    assert eps[0]["reachable"] is True and eps[0]["status"] == 200
    assert eps[1]["reachable"] is False


def test_collectors_registry_complete():
    assert set(COLLECTORS) == {
        "process", "logs", "system", "database", "llm_gateway", "bank_api",
    }
