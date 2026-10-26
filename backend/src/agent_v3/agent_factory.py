"""agent_v3 ReActAgent 进程级单例组装（镜像 v2 agent_factory 模式）。

openjiuwen 导入隔离：全仓库仅 agent_v3 包内允许 import openjiuwen。
"""
from __future__ import annotations

import asyncio
import logging

from openjiuwen.core.context_engine import (
    ContextEngineConfig,
    DialogueCompressorConfig,
    MessageOffloaderConfig,
)
from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig
from openjiuwen.core.runner import Runner
from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig
from openjiuwen.core.sys_operation import (
    LocalWorkConfig,
    OperationMode,
    SysOperationCard,
)
from openjiuwen.harness.prompts.sections.reload import RELOAD_HINT_CN
from openjiuwen.harness.tools import ReadFileTool
from openjiuwen.harness.workspace.workspace import Workspace

from src.agent_v3.prompts.system import build_system_prompt
from src.agent_v3.tools import WRITE_TOOLS
from src.agent_v3.rails import (
    ApprovalEditRail,
    ToolCallLimitRail,
    ToolProgressRail,
    UnknownToolGuardRail,
)
from src.agent_v3.tools import ALL_V3_TOOLS
from src.config import get_settings, resolve_path
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
        use_shared_llm_http_client=False,
        verify_ssl=settings.llm_verify_ssl,
    )
    request_cfg = ModelRequestConfig(
        model=settings.agent_v2_main_llm_model or settings.llm_model,
        temperature=resolve_temperature(settings, "agent_v2_main"),
    )
    return client_cfg, request_cfg


def build_v3_context_configs(settings, client_cfg, request_cfg):
    if settings.agent_v3_context_offload_trim_size >= settings.agent_v3_context_offload_large_message_threshold:
        raise ValueError("AGENT_V3_CONTEXT_OFFLOAD_TRIM_SIZE 必须小于大消息阈值")
    if settings.agent_v3_context_reload_enabled and not settings.agent_v3_context_offload_enabled:
        raise ValueError("AGENT_V3_CONTEXT_RELOAD_ENABLED 要求同时启用 offload")

    engine_config = ContextEngineConfig(
        default_window_round_num=settings.agent_v3_context_window_rounds or None,
        enable_reload=settings.agent_v3_context_reload_enabled,
        context_window_tokens=settings.agent_v2_main_llm_max_tokens or settings.llm_max_tokens,
        model_name=request_cfg.model_name,
    )
    processors = []
    if settings.agent_v3_context_offload_enabled:
        processors.append((
            "MessageOffloader",
            MessageOffloaderConfig(
                tokens_threshold=settings.agent_v3_context_offload_tokens_threshold,
                large_message_threshold=settings.agent_v3_context_offload_large_message_threshold,
                trim_size=settings.agent_v3_context_offload_trim_size,
                messages_to_keep=settings.agent_v3_context_messages_to_keep,
                keep_last_round=True,
                offload_message_type=["tool"],
            ),
        ))
    if settings.agent_v3_context_compression_enabled:
        processors.append((
            "DialogueCompressor",
            DialogueCompressorConfig(
                tokens_threshold=settings.agent_v3_context_compression_tokens_threshold,
                compression_target_tokens=settings.agent_v3_context_compression_target_tokens,
                messages_to_keep=settings.agent_v3_context_messages_to_keep,
                keep_last_round=True,
                model=request_cfg,
                model_client=client_cfg,
            ),
        ))
    return engine_config, processors


_CONTEXT_SYS_OPERATION_ID = "agent-v3-context-offload"
_RELOAD_TOOL_NAME = "read_file"


def build_v3_reload_config(settings):
    if not settings.agent_v3_context_reload_enabled:
        return None, None
    workspace = Workspace(
        root_path=str(resolve_path(settings.agent_v3_context_workspace_dir).resolve()),
        language="cn",
    )
    return workspace, _CONTEXT_SYS_OPERATION_ID


def get_v3_reload_operation(settings):
    operation = Runner.resource_mgr.get_sys_operation(_CONTEXT_SYS_OPERATION_ID)
    if operation is not None:
        return operation
    workspace_root = str(resolve_path(settings.agent_v3_context_workspace_dir).resolve())
    card = SysOperationCard(
        id=_CONTEXT_SYS_OPERATION_ID,
        mode=OperationMode.LOCAL,
        work_config=LocalWorkConfig(
            restrict_to_sandbox=True,
            sandbox_root=[workspace_root],
        ),
    )
    result = Runner.resource_mgr.add_sys_operation(card)
    if not result.is_ok():
        raise RuntimeError(f"注册上下文恢复文件操作失败: {result.msg()}")
    return Runner.resource_mgr.get_sys_operation(_CONTEXT_SYS_OPERATION_ID)


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
        context_engine_config, context_processors = build_v3_context_configs(
            settings, client_cfg, request_cfg,
        )
        workspace, sys_operation_id = build_v3_reload_config(settings)
        config = ReActAgentConfig(
            model_config_obj=request_cfg,
            model_client_config=client_cfg,
            prompt_template=[{"role": "system", "content": build_system_prompt()}],
            max_iterations=settings.agent_v3_max_iterations,
            context_engine_config=context_engine_config,
            context_processors=context_processors,
            workspace=workspace,
            sys_operation_id=sys_operation_id,
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
        known_tools = [t.card.name for t in ALL_V3_TOOLS]
        if settings.agent_v3_context_reload_enabled:
            operation = get_v3_reload_operation(settings)
            read_tool = ReadFileTool(
                operation, "cn", agent.card.id, enable_image_multimodal=False,
            )
            agent.ability_manager.add_ability(read_tool.card, read_tool)
            known_tools.append(_RELOAD_TOOL_NAME)
            agent.add_prompt_builder_section(
                "offload",
                RELOAD_HINT_CN + "\n\n在此恢复流程中允许调用内置 read_file，且只能读取 OFFLOAD marker 提供的精确 path。",
                priority=90,
            )
        await agent.register_rail(ApprovalEditRail(tool_names=sorted(WRITE_TOOLS)))
        # generate_report 条件审批：已有报告时重新生成会覆盖当前报告，须用户确认；
        # 首次生成（报告页首条消息）无报告可覆盖，rail 自动放行，不破坏原有流程。
        await agent.register_rail(ApprovalEditRail(
            tool_names=["generate_report"],
            require_existing_report=True,
        ))
        # 幻觉工具拦截须先于 ToolCallLimitRail：被拦截的调用不执行、不计额度
        await agent.register_rail(UnknownToolGuardRail(known_tools=known_tools))
        await agent.register_rail(ToolCallLimitRail(max_calls=settings.agent_v3_max_tool_calls_per_run))
        await agent.register_rail(ToolProgressRail())
        _agent = agent
        logger.info("agent_v3 ReActAgent initialized, tools=%s", known_tools)
        return _agent


async def close_v3_agent() -> None:
    """main.py lifespan shutdown 调用（Runner.stop 由 lifespan 统一负责）。"""
    global _agent
    _agent = None
