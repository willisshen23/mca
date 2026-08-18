from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from src.diagnosis.llm import chat
from src.diagnosis.prompts import SYSTEM_PROMPT, render_diagnosis_messages


def _llm_settings(settings):
    settings.llm_base_url = "http://gw:4000/v1"
    settings.llm_api_key = "sk-x"
    settings.llm_model = "deepseek"
    return settings


def test_chat_returns_content(settings):
    _llm_settings(settings)

    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "deepseek"
        assert body["messages"][0]["role"] == "system"
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"causes\":[]}"}}]})

    result = asyncio.run(
        chat(settings, [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
             transport=httpx.MockTransport(handler))
    )
    assert result == '{"causes":[]}'


def test_chat_raises_on_http_error(settings):
    _llm_settings(settings)

    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(chat(settings, [{"role": "user", "content": "u"}],
                         transport=httpx.MockTransport(handler)))


def test_render_messages_contract():
    check = {"id": "llm-latency", "title": "LLM 网关延迟", "level": "red", "message": "超时 45s"}
    evidence = {"check": check, "samples": {}, "app_config": {}}

    messages = render_diagnosis_messages(check, evidence, "网关超时手册正文")

    assert messages[0]["role"] == "system"
    assert "JSON" in messages[0]["content"]
    user = messages[1]["content"]
    assert "llm-latency" in user
    assert "超时 45s" in user
    assert "网关超时手册正文" in user


def test_render_messages_with_empty_runbook():
    check = {"id": "x", "title": "x", "level": "red", "message": "m"}
    messages = render_diagnosis_messages(check, {"samples": {}}, "")
    assert "（无匹配运维手册）" in messages[1]["content"]
