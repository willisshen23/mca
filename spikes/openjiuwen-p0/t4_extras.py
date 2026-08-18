# P0 附加验证（对应调研文档 §5.7 未验证项 + 迁移映射表遗留点）：
#   A. max_iterations 可配置且真实生效（live）
#   B. @tool 在 `from __future__ import annotations` 下 schema 抽取正常（本地，langchain 时代的老坑）
#   C. 每轮工具调用上限无内置配置，验证自定义 Rail 计数拦截可行（live）
#   D. 上下文裁剪：ContextEngineConfig 提供窗口/压缩配置项（源码证据，打印默认值）
from __future__ import annotations  # 故意放在文件顶部验证 B

import asyncio
import os
import sys

from openjiuwen.core.runner import Runner
from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig
from openjiuwen.core.single_agent.rail.base import AgentRail, AgentCallbackContext
from openjiuwen.core.foundation.llm import ModelClientConfig, ModelRequestConfig, ToolMessage
from openjiuwen.core.foundation.tool import tool

sys.path.insert(0, os.path.dirname(__file__))
from t1_model_toolcall import load_backend_env

CALL_LOG = []


@tool
def record_metric(metric_name: str, value: float) -> str:
    """记录一个营销指标数值。参数：metric_name 指标名，value 数值。"""
    CALL_LOG.append({"metric_name": metric_name, "value": value})
    return f"已记录 {metric_name}={value}"


def check_b_annotation_extraction():
    """B: future annotations 下 @tool 的 input_params 抽取"""
    params = record_metric.card.input_params
    print("[B] future-annotations 下抽取的 input_params:", params)
    props = params.get("properties", {})
    assert set(props) == {"metric_name", "value"}, f"schema 抽取异常: {params}"
    assert params.get("required") == ["metric_name", "value"]
    print("[B] PASS: from __future__ import annotations 不影响 @tool schema 抽取")


def _make_agent(max_iterations=None, rail=None):
    env = load_backend_env()
    kwargs = dict(
        model_config_obj=ModelRequestConfig(model=env["LLM_MODEL"], temperature=0.1),
        model_client_config=ModelClientConfig(
            client_provider="OpenAI", api_key=env["LLM_API_KEY"],
            api_base=env["LLM_BASE_URL"], timeout=120),
        prompt_template=[{"role": "system", "content":
            "你是营销数据助手。用户要求记录指标时，逐条调用 record_metric 工具，每条指标调用一次。"}],
    )
    if max_iterations is not None:
        kwargs["max_iterations"] = max_iterations
    agent = ReActAgent(card=AgentCard(id=f"spike_t4_{id(kwargs)}", description="spike")).configure(
        ReActAgentConfig(**kwargs))
    agent.ability_manager.add(record_metric.card)
    return agent


async def check_a_max_iterations():
    """A: max_iterations=1 时，工具执行后没有剩余迭代生成最终答复 → error 结果，证明上限生效"""
    agent = _make_agent(max_iterations=1)
    try:
        Runner.resource_mgr.add_tool(record_metric)
    except Exception:
        pass
    r = await Runner.run_agent(agent, {"query": "记录指标：转化率=5.2"}, session="spike-t4-maxiter")
    print(f"[A] max_iterations=1 结果: result_type={r.get('result_type')} output={str(r.get('output'))[:80]}")
    assert r.get("result_type") == "error" and "Max iterations" in str(r.get("output")), \
        f"期望 max-iterations error，实际: {r}"
    print("[A] PASS: max_iterations 配置真实生效（默认 5，可调整）")


class ToolCallLimitRail(AgentRail):
    """C: 自定义 Rail 实现『同一工具每次运行最多调用 N 次』——替代 ToolCallLimitMiddleware"""

    def __init__(self, tool_name: str, max_calls: int):
        self._tool_name = tool_name
        self._max_calls = max_calls
        self._count = 0

    async def before_tool_call(self, ctx: AgentCallbackContext) -> None:
        if ctx.inputs.tool_name != self._tool_name:
            return
        self._count += 1
        if self._count > self._max_calls:
            tool_call = ctx.inputs.tool_call
            tool_call_id = getattr(tool_call, "id", "") if tool_call else ""
            ctx.extra["_skip_tool"] = True
            ctx.inputs.tool_result = f"调用次数超限（{self._max_calls} 次/轮），已跳过"
            ctx.inputs.tool_msg = ToolMessage(content=ctx.inputs.tool_result, tool_call_id=tool_call_id)
            print(f"[C] rail 拦截第 {self._count} 次调用，已跳过")


async def check_c_tool_call_limit():
    """C: 自定义计数 Rail 拦截超限调用"""
    agent = _make_agent()
    rail = ToolCallLimitRail(tool_name="record_metric", max_calls=2)
    await agent.register_rail(rail)
    CALL_LOG.clear()
    r = await Runner.run_agent(
        agent,
        {"query": "请依次记录三个指标：转化率=5.2，点击率=3.1，响应率=8.8"},
        session="spike-t4-lmit")
    print(f"[C] result_type={r.get('result_type')} 实际执行次数={len(CALL_LOG)} rail计数={rail._count}")
    print(f"[C] final output: {str(r.get('output'))[:120]}")
    assert len(CALL_LOG) == 2, f"应只执行 2 次，实际 {len(CALL_LOG)}"
    assert rail._count >= 3, "rail 应观察到至少 3 次调用意图"
    assert r.get("result_type") == "answer"
    print("[C] PASS: 自定义 Rail 可实现工具调用上限（无内置配置，需自研）")


def check_d_context_config():
    """D: 上下文裁剪配置项存在性（源码级）"""
    cfg = ReActAgentConfig()
    ce = cfg.context_engine_config
    print(f"[D] ContextEngineConfig: max_context_message_num={ce.max_context_message_num} "
          f"default_window_round_num={ce.default_window_round_num} context_processors={cfg.context_processors}")
    print("[D] PASS: 窗口/轮次裁剪配置存在（另有 dialogue_compressor 等 processor，默认不启用）")


async def main():
    check_b_annotation_extraction()
    check_d_context_config()
    await Runner.start()
    try:
        await check_a_max_iterations()
        await check_c_tool_call_limit()
    finally:
        await Runner.stop()
    print("VERIFY-4 PASS: 附加验证全部通过")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
