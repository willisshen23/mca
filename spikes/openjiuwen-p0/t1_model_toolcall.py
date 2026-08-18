# P0 验证①：行内 deepseek 端点（OpenAI 兼容）经 ModelClientConfig 可用 + tool calling 正常
# 端点配置直接复用 backend/.env（M1 已验收该端点 tool calling 可用）
import asyncio
import os
import sys

from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig


def load_backend_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env")
    cfg = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


async def main():
    env = load_backend_env()
    client_cfg = ModelClientConfig(
        client_provider="OpenAI",
        api_key=env["LLM_API_KEY"],
        api_base=env["LLM_BASE_URL"],  # https://api.deepseek.com
        timeout=120,
        verify_ssl=True,
    )
    model_cfg = ModelRequestConfig(model=env["LLM_MODEL"], temperature=0.1)  # deepseek-v4-flash
    model = Model(model_client_config=client_cfg, model_config=model_cfg)

    # 1) 普通对话
    resp = await model.invoke([{"role": "user", "content": "用一句话回答：1+1等于几？"}])
    print("[chat] content:", (resp.content or "")[:100])
    assert resp.content, "chat 无内容返回"

    # 2) tool calling
    tools = [{
        "type": "function",
        "function": {
            "name": "get_activity_detail",
            "description": "查询营销活动详情",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_id": {"type": "string", "description": "活动ID"},
                },
                "required": ["activity_id"],
            },
        },
    }]
    resp2 = await model.invoke(
        [{"role": "user", "content": "帮我查活动 A20260807 的详情"}],
        tools=tools,
    )
    tool_calls = getattr(resp2, "tool_calls", None)
    print("[tool_call] tool_calls:", tool_calls)
    assert tool_calls, "未返回 tool_calls"
    tc = tool_calls[0]
    name = tc.name if hasattr(tc, "name") else tc.get("function", {}).get("name")
    args = tc.arguments if hasattr(tc, "arguments") else tc.get("function", {}).get("arguments")
    print(f"[tool_call] name={name} args={args}")
    assert name == "get_activity_detail"
    assert "A20260807" in str(args)
    print("VERIFY-1 PASS: OpenAI 兼容端点对话与 tool calling 均正常")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
