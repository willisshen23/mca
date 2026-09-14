"""agent_v3 ReActAgent 进程级单例组装（镜像 v2 agent_factory 模式）。

openjiuwen 导入隔离：全仓库仅 agent_v3 包内允许 import openjiuwen。
"""
from __future__ import annotations

import asyncio
import logging

from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
from openjiuwen.core.runner import Runner
from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig

from src.agent_v3.prompts.system import build_system_prompt
from src.agent_v3.tools import WRITE_TOOLS
from src.agent_v3.rails import (
    ApprovalEditRail,
    ToolCallLimitRail,
    ToolProgressRail,
    UnknownToolGuardRail,
)
from src.agent_v3.tools import ALL_V3_TOOLS
from src.config import get_settings
from src.llm import LoggingModel, resolve_temperature

logger = logging.getLogger("activity-analysis.agent")


def build_v3_model_configs(settings) -> tuple[ModelClientConfig, ModelRequestConfig]:
    """模型配置：agent_v2_main 角色优先，缺省回退全局 llm_*（与 get_llm 同语义）。"""
    client_cfg = ModelClientConfig(
        client_provider="OpenAI",
        api_key=settings.agent_v2_main_llm_api_key or settings.llm_api_key,
        api_base=settings.agent_v2_main_llm_base_url or settings.llm_base_url,
        timeout=120,
        # SDK 默认 3 次重试会把 429 限流放大成最多 4 倍实际请求，显式压低
        max_retries=settings.llm_max_retries,
        verify_ssl=settings.llm_verify_ssl,
    )
    request_cfg = ModelRequestConfig(
        model=settings.agent_v2_main_llm_model or settings.llm_model,
        temperature=resolve_temperature(settings, "agent_v2_main"),
    )
    return client_cfg, request_cfg


_agent: ReActAgent | None = None
_lock = asyncio.Lock()


async def get_v3_agent() -> ReActAgent:
    global _agent
    if _agent is not None:
        return _agent
    async with _lock:
        if _agent is not None:
            return _agent
        settings = get_settings()
        client_cfg, request_cfg = build_v3_model_configs(settings)
        config = ReActAgentConfig(
            model_config_obj=request_cfg,
            model_client_config=client_cfg,
            prompt_template=[{"role": "system", "content": build_system_prompt()}],
            max_iterations=settings.agent_v3_max_iterations,
        )
        agent = ReActAgent(card=AgentCard(
            id="activity-analysis-marketing-agent-v3",
            description="营销分析助手 v3",
        )).configure(config)
        # 注入日志包装：每次访问大模型都把输入信息打印到日志
        model = LoggingModel(
            client_cfg, request_cfg,
            label=settings.agent_v2_main_llm_model or settings.llm_model or "agent_v3",
        )
        agent.set_llm(model)
        for t in ALL_V3_TOOLS:
            Runner.resource_mgr.add_tool(t)
            agent.ability_manager.add(t.card)
        await agent.register_rail(ApprovalEditRail(tool_names=sorted(WRITE_TOOLS)))
        # generate_report 条件审批：已有报告时重新生成会覆盖当前报告，须用户确认；
        # 首次生成（报告页首条消息）无报告可覆盖，rail 自动放行，不破坏原有流程。
        await agent.register_rail(ApprovalEditRail(
            tool_names=["generate_report"],
            require_existing_report=True,
        ))
        # 幻觉工具拦截须先于 ToolCallLimitRail：被拦截的调用不执行、不计额度
        await agent.register_rail(
            UnknownToolGuardRail(known_tools=[t.card.name for t in ALL_V3_TOOLS])
        )
        await agent.register_rail(ToolCallLimitRail(max_calls=settings.agent_v3_max_tool_calls_per_run))
        await agent.register_rail(ToolProgressRail())
        _agent = agent
        logger.info("agent_v3 ReActAgent initialized, tools=%s",
                    [t.card.name for t in ALL_V3_TOOLS])
        return _agent


async def close_v3_agent() -> None:
    """main.py lifespan shutdown 调用（Runner.stop 由 lifespan 统一负责）。"""
    global _agent
    _agent = None
