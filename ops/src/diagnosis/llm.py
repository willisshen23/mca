from __future__ import annotations

import httpx


async def chat(settings, messages: list[dict], transport=None) -> str:
    """OpenAI 兼容网关单次 chat 调用，返回 content 字符串。"""
    headers = {}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    async with httpx.AsyncClient(
        timeout=settings.llm_timeout_s, transport=transport
    ) as client:
        resp = await client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            json={
                "model": settings.llm_model,
                "messages": messages,
                "temperature": 0.2,
            },
            headers=headers,
        )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
