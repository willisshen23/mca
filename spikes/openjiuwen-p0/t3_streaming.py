# P0 验证③：run_agent_streaming 产出 OutputSchema/CustomSchema，可逐帧桥接 SSE
# 同时覆盖 §5.7 未验证项：interrupt 前后流式完整性（流式中断帧 + 流式恢复）
import asyncio
import json
import os
import sys

from openjiuwen.core.runner import Runner
from openjiuwen.core.session import InteractiveInput
from openjiuwen.core.session.stream import OutputSchema, CustomSchema
from openjiuwen.harness.rails.interrupt.confirm_rail import ConfirmInterruptRail

sys.path.insert(0, os.path.dirname(__file__))
from t2_hitl_interrupt import build_agent, modify_report, WRITE_LOG


def summarize_chunk(chunk):
    if isinstance(chunk, OutputSchema):
        payload = chunk.payload
        if isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[1], dict):
            body = payload[1]
        elif hasattr(payload, "model_dump"):
            body = payload.model_dump()
        else:
            body = payload
        return ("OutputSchema", chunk.type, json.dumps(body, ensure_ascii=False, default=str)[:160])
    if isinstance(chunk, CustomSchema):
        return ("CustomSchema", None, str(chunk)[:160])
    return (type(chunk).__name__, getattr(chunk, "type", None), str(chunk)[:160])


async def scenario_stream_chat():
    """场景1：纯对话流式 —— token 级增量，逐帧可转 SSE"""
    agent = build_agent()
    chunks = []
    async for chunk in Runner.run_agent_streaming(
            agent, {"query": "用两句话介绍的数字化转型。"}, session="spike-stream-chat"):
        chunks.append(chunk)
    types = [getattr(c, "type", type(c).__name__) for c in chunks]
    from collections import Counter
    print("[stream-chat] chunk type 分布:", dict(Counter(types)))
    for c in chunks[:5]:
        print("[stream-chat] 首帧样例:", summarize_chunk(c))
    # 拼接 llm_output（token 级内容帧）验证增量；answer 为最终聚合帧
    answer_parts = []
    final_frame = None
    for c in chunks:
        if isinstance(c, OutputSchema) and c.type == "llm_output":
            p = c.payload
            if isinstance(p, dict):
                answer_parts.append(p.get("content", ""))
            elif isinstance(p, tuple) and len(p) == 2 and isinstance(p[1], dict):
                answer_parts.append(p[1].get("content", ""))
        elif isinstance(c, OutputSchema) and c.type == "answer":
            final_frame = c
    full = "".join(answer_parts)
    print(f"[stream-chat] llm_output 帧数={len(answer_parts)} 拼接后长度={len(full)} 内容预览={full[:80]}")
    print(f"[stream-chat] 最终 answer 帧: {str(final_frame.payload)[:120] if final_frame else None}")
    assert len(chunks) > 1, "流式应产出多帧"
    assert len(answer_parts) > 1, f"token 级流式应产出多个 llm_output 帧，实际 {len(answer_parts)}"
    assert len(full) > 20, "拼接后的回答过短，流式内容可能不完整"
    assert final_frame is not None, "应有最终 answer 帧作为完成标记"
    print("[stream-chat] PASS: token 级流式正常，帧结构可逐帧转 SSE")


async def scenario_stream_interrupt():
    """场景2：流式中的写工具审批 —— __interaction__ 帧 + 流式恢复"""
    agent = build_agent()
    await agent.register_rail(ConfirmInterruptRail(tool_names=["modify_report"]))
    session_id = "spike-stream-hitl"

    WRITE_LOG.clear()
    pre_chunks, interaction_ids = [], []
    async for chunk in Runner.run_agent_streaming(
            agent, {"query": "帮我把报告标题改成《开门红活动总结》，正文写：超额完成。"},
            session=session_id):
        pre_chunks.append(chunk)
        if isinstance(chunk, OutputSchema) and chunk.type == "__interaction__":
            interaction_ids.append(chunk.payload.id)
    print("[stream-hitl] 中断前帧类型:", [getattr(c, "type", "?") for c in pre_chunks])
    assert interaction_ids, "流式中应出现 __interaction__ 帧"
    assert WRITE_LOG == [], "中断时写工具不应执行"

    # 流式恢复：approve
    ii = InteractiveInput()
    ii.update(interaction_ids[0], {"approved": True, "feedback": "", "auto_confirm": False})
    post_chunks = []
    async for chunk in Runner.run_agent_streaming(agent, {"query": ii}, session=session_id):
        post_chunks.append(chunk)
    post_types = [getattr(c, "type", type(c).__name__) for c in post_chunks]
    print("[stream-hitl] 恢复后帧类型:", post_types[:20])
    answer_parts = []
    for c in post_chunks:
        if isinstance(c, OutputSchema) and c.type == "llm_output":
            p = c.payload
            if isinstance(p, dict):
                answer_parts.append(p.get("content", ""))
            elif isinstance(p, tuple) and len(p) == 2 and isinstance(p[1], dict):
                answer_parts.append(p[1].get("content", ""))
    full = "".join(answer_parts)
    print(f"[stream-hitl] 恢复后 llm_output 帧数={len(answer_parts)} 预览={full[:80]}")
    assert len(WRITE_LOG) == 1, "approve 后写工具应执行一次"
    assert answer_parts and len(full) > 5, "恢复后应有完整流式回答"
    print("[stream-hitl] PASS: __interaction__ 帧出现，流式恢复后回答完整")


async def main():
    await Runner.start()
    try:
        await scenario_stream_chat()
        await scenario_stream_interrupt()
    finally:
        await Runner.stop()
    print("VERIFY-3 PASS: run_agent_streaming 可桥接 SSE（token 流 + 中断帧 + 流式恢复）")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
