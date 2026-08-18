# P0 验证②：ReActAgent + 写工具 + ConfirmInterruptRail 走完 interrupt → InteractiveInput resume 全流程
# 覆盖 approve / reject 两条路径
import asyncio
import json
import os
import sys

from openjiuwen.core.foundation.llm import ModelClientConfig, ModelRequestConfig
from openjiuwen.core.foundation.tool import tool
from openjiuwen.core.runner import Runner
from openjiuwen.core.session import InteractiveInput
from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig
from openjiuwen.harness.rails.interrupt.confirm_rail import ConfirmInterruptRail

sys.path.insert(0, os.path.dirname(__file__))
from t1_model_toolcall import load_backend_env

# 模拟写工具：记录真实副作用，用于断言"中断时未执行 / 批准后执行 / 拒绝后不执行"
WRITE_LOG = []


@tool
def modify_report(title: str, content: str) -> str:
    """修改营销分析报告（写操作，需人工审批）。参数：title 报告标题，content 报告正文。"""
    WRITE_LOG.append({"title": title, "content": content})
    return f"报告已修改：标题={title}，正文长度={len(content)}"


def build_agent():
    env = load_backend_env()
    cfg = ReActAgentConfig(
        model_config_obj=ModelRequestConfig(model=env["LLM_MODEL"], temperature=0.1),
        model_client_config=ModelClientConfig(
            client_provider="OpenAI",
            api_key=env["LLM_API_KEY"],
            api_base=env["LLM_BASE_URL"],
            timeout=120,
        ),
        prompt_template=[{
            "role": "system",
            "content": "你是银行营销分析助手。用户要求修改报告时，必须调用 modify_report 工具，不要自己编造结果。",
        }],
    )
    agent = ReActAgent(card=AgentCard(id="spike_agent", description="spike")).configure(cfg)
    Runner.resource_mgr.add_tool(modify_report)
    agent.ability_manager.add(modify_report.card)
    return agent


async def scenario_approve():
    """路径1：interrupt → approve → 工具真正执行"""
    agent = build_agent()
    await agent.register_rail(ConfirmInterruptRail(tool_names=["modify_report"]))
    session_id = "spike-hitl-approve"

    WRITE_LOG.clear()
    r1 = await Runner.run_agent(agent, {"query": "帮我把报告标题改成《暑期营销活动分析》，正文写：本次活动转化率提升5%。"},
                                session=session_id)
    print("[approve] first run result_type:", r1.get("result_type"))
    print("[approve] interrupt_ids:", r1.get("interrupt_ids"))
    assert r1.get("result_type") == "interrupt", f"期望 interrupt，实际 {r1.get('result_type')}: {r1}"
    assert WRITE_LOG == [], "中断时写工具不应执行"
    interrupt_id = r1["interrupt_ids"][0]
    state0 = r1.get("state")
    if state0:
        payload = getattr(state0[0], "payload", state0[0])
        print("[approve] interrupt payload:", str(payload)[:300])

    # 恢复：approve
    ii = InteractiveInput()
    ii.update(interrupt_id, {"approved": True, "feedback": "", "auto_confirm": False})
    r2 = await Runner.run_agent(agent, {"query": ii}, session=session_id)
    print("[approve] resume result_type:", r2.get("result_type"))
    print("[approve] resume output:", str(r2.get("output"))[:200])
    assert r2.get("result_type") == "answer", f"恢复后期望 answer，实际 {r2.get('result_type')}: {r2}"
    assert len(WRITE_LOG) == 1, "approve 后写工具应执行一次"
    assert "暑期营销活动分析" in WRITE_LOG[0]["title"]
    print("[approve] PASS: interrupt -> approve -> 工具执行")


async def scenario_reject():
    """路径2：interrupt → reject(feedback) → 工具不执行，feedback 回传模型"""
    agent = build_agent()
    await agent.register_rail(ConfirmInterruptRail(tool_names=["modify_report"]))
    session_id = "spike-hitl-reject"

    WRITE_LOG.clear()
    r1 = await Runner.run_agent(agent, {"query": "帮我把报告标题改成《国庆大促复盘》，正文写：全部达标。"},
                                session=session_id)
    assert r1.get("result_type") == "interrupt", f"期望 interrupt，实际 {r1.get('result_type')}: {r1}"
    interrupt_id = r1["interrupt_ids"][0]

    ii = InteractiveInput()
    ii.update(interrupt_id, {"approved": False, "feedback": "标题不要用书名号", "auto_confirm": False})
    r2 = await Runner.run_agent(agent, {"query": ii}, session=session_id)
    print("[reject] resume#1 result_type:", r2.get("result_type"))

    # reject 后模型可能按 feedback 重试工具 → 再次 interrupt，这是预期行为（二次审批）。
    # 循环拒绝直至模型放弃写操作给出最终答复。
    rounds = 1
    while r2.get("result_type") == "interrupt" and rounds < 4:
        rounds += 1
        ii = InteractiveInput()
        ii.update(r2["interrupt_ids"][0],
                  {"approved": False, "feedback": "用户已取消本次修改，不要再调用工具，直接回复", "auto_confirm": False})
        r2 = await Runner.run_agent(agent, {"query": ii}, session=session_id)
        print(f"[reject] resume#{rounds} result_type:", r2.get("result_type"))

    print("[reject] final output:", str(r2.get("output"))[:200])
    assert r2.get("result_type") == "answer", f"恢复后期望 answer，实际 {r2.get('result_type')}: {r2}"
    assert WRITE_LOG == [], "reject 后写工具不应执行"
    print(f"[reject] PASS: interrupt -> reject（{rounds} 轮拒绝）-> 工具未执行，模型收到 feedback 并回应")


async def main():
    await Runner.start()
    try:
        await scenario_approve()
        await scenario_reject()
    finally:
        await Runner.stop()
    print("VERIFY-2 PASS: ConfirmInterruptRail 中断/恢复（approve+reject）全流程通过")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
