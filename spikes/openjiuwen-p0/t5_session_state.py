# P1 前置验证（计划依据）：
#   E. 工具内 get_current_session().get_state/update_state（注意：不是 get_global_state）跨 run 持久（同 session id，in-memory）
#   F. 工具内 write_custom_stream 的自定义帧出现在 run_agent_streaming 输出中（替代 langgraph get_stream_writer）
import asyncio
import os
import sys

from openjiuwen.core.runner import Runner
from openjiuwen.core.session import get_current_session
from openjiuwen.core.session.stream import OutputSchema, CustomSchema, BaseStreamMode
from openjiuwen.core.foundation.tool import tool
from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig
from openjiuwen.core.foundation.llm import ModelClientConfig, ModelRequestConfig

sys.path.insert(0, os.path.dirname(__file__))
from t1_model_toolcall import load_backend_env


@tool
async def remember_activity(activity_id: str) -> str:
    """把活动编号记入会话分析队列。参数：activity_id 活动编号。"""
    session = get_current_session()
    queue = session.get_state("analysis_queue") or []
    queue = list(queue) + [activity_id]
    session.update_state({"analysis_queue": queue})
    await session.write_custom_stream({"step": "remember_activity", "status": "done"})
    return f"已记住活动 {activity_id}，当前队列长度 {len(queue)}"


@tool
async def read_queue() -> str:
    """读取当前会话分析队列。"""
    session = get_current_session()
    queue = session.get_state("analysis_queue") or []
    return f"当前队列：{queue}"


def build_agent():
    env = load_backend_env()
    cfg = ReActAgentConfig(
        model_config_obj=ModelRequestConfig(model=env["LLM_MODEL"], temperature=0.1),
        model_client_config=ModelClientConfig(
            client_provider="OpenAI", api_key=env["LLM_API_KEY"],
            api_base=env["LLM_BASE_URL"], timeout=120),
        prompt_template=[{"role": "system", "content":
            "你是营销分析助手。用户要求记住活动时调用 remember_activity；询问队列时调用 read_queue。"}],
    )
    agent = ReActAgent(card=AgentCard(id="spike_t5", description="spike")).configure(cfg)
    Runner.resource_mgr.add_tool(remember_activity)
    Runner.resource_mgr.add_tool(read_queue)
    agent.ability_manager.add(remember_activity.card)
    agent.ability_manager.add(read_queue.card)
    return agent


async def main():
    await Runner.start()
    try:
        agent = build_agent()
        sid = "spike-t5-state"

        # E1: run#1 写入全局状态 + 收集 custom 帧
        custom_frames = []
        async for chunk in Runner.run_agent_streaming(
                agent, {"query": "帮我记住活动 ACT001"}, session=sid,
                stream_modes=[BaseStreamMode.OUTPUT, BaseStreamMode.CUSTOM]):
            if isinstance(chunk, CustomSchema):
                custom_frames.append(chunk)
        print("[E/F] run#1 custom 帧:", [str(c)[:120] for c in custom_frames])
        assert any("remember_activity" in str(c) for c in custom_frames), \
            "write_custom_stream 的自定义帧应出现在流式输出中"
        print("[F] PASS: write_custom_stream 帧可桥接（替代 get_stream_writer）")

        # E2: run#2 同 session id，读取 run#1 写入的状态
        r2 = await Runner.run_agent(agent, {"query": "现在队列里有什么？"}, session=sid)
        out = str(r2.get("output"))
        print("[E] run#2 output:", out[:200])
        assert "ACT001" in out, f"跨 run 全局状态未保持: {out[:200]}"
        print("[E] PASS: 全局状态跨 run（同 session id）持久")
    finally:
        await Runner.stop()
    print("VERIFY-5 PASS: 会话全局状态 + 自定义流帧两条迁移关键路径可用")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
