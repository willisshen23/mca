"""LLM 访问层（openjiuwen Model）：角色化工厂 + 上下文预算守卫 + io 日志/用量落库。

替代原 config.get_llm（v2 旧框架 ChatOpenAI 栈）。角色配置语义与旧 get_llm 一致：
settings.{role}_llm_api_key/base_url/model/max_tokens，缺省回退全局 llm_*。

模型客户端设计约束：

1. 报告管线在独立线程的 ``asyncio.run`` 中执行并关闭事件循环，进程级共享
   HTTP 客户端会因此把失效连接带回主对话。所有模型配置统一设置
   ``use_shared_llm_http_client=False``，每次请求使用并关闭独立客户端。
   逐请求超时仍经 ``Model.invoke(..., timeout=秒)`` 透传。
2. openjiuwen 把所有底层异常包成
   ``openjiuwen.core.common.exception.errors.FrameworkError``，原始 openai SDK
   异常保留在 ``__cause__``（如 APITimeoutError / AuthenticationError）。判定
   供应商上下文超限错误时须沿 ``__cause__`` 链检查，见 ``_iter_causes``。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Iterator
from uuid import uuid4

from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig

from src.config import get_settings
from src.infrastructure.db.session import SessionLocal
from src.utils.token_budget import (
    ModelContextLengthExceeded,
    estimate_model_request_tokens,
    is_provider_context_limit_error,
)

logger = logging.getLogger("activity-analysis.agent")

_model_cache: dict[str, "GuardedModel"] = {}


def reset_model_cache() -> None:
    _model_cache.clear()


def _iter_causes(exc: BaseException) -> Iterator[BaseException]:
    """沿异常链产出 exc 自身及全部成因。

    优先走显式 ``__cause__``；未设置时回退隐式 ``__context__``（Python 异常链
    语义：显式 cause 会抑制 context）。带 id 去重防御成环。
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ if current.__cause__ is not None else current.__context__


# 输入序列化：兼容 str / dict / openjiuwen BaseMessage / List 混合形态
def _serialize_message(msg: Any) -> str:
    """把单条消息转成可读日志文本。"""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        role = str(msg.get("role") or "")
        content = msg.get("content", "")
        if isinstance(content, list):
            try:
                content = json.dumps(content, ensure_ascii=False)
            except (TypeError, ValueError):
                content = str(content)
        return f"[{role}] {content}" if role else str(content)
    role = str(getattr(msg, "role", "") or getattr(msg, "type", "") or "")
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        try:
            content = json.dumps(content, ensure_ascii=False)
        except (TypeError, ValueError):
            content = str(content)
    return f"[{role}] {content}" if role else str(content)


def serialize_messages(messages: Any) -> str:
    """把 LLM 输入（str / dict / 消息对象 / 消息列表）序列化为可读日志文本。"""
    if messages is None:
        return ""
    if isinstance(messages, list):
        return "\n".join(_serialize_message(msg) for msg in messages)
    return _serialize_message(messages)


class LoggingModel:
    """openjiuwen Model 的日志包装：每次 invoke/stream 前把输入打印到日志。

    用于 agent_v3 ReActAgent 主对话链路（框架内部持有多轮消息，无法在调用点
    逐一插桩，故通过 set_llm 注入本包装，在唯一入口统一记录输入）。

    与框架自身一致采用懒初始化：构造时不构建底层 client（避免在仅有配置、
    尚未真正调用大模型时触发 ssl/密钥校验），首次 invoke/stream 才按配置
    创建真实 Model。

    注意：刻意不继承 openjiuwen Model。框架 react_agent 在调用前会无条件
    探测 supports_kv_cache_release / build_kv_cache_invoke_kwargs 等能力
    方法，若继承 Model 而不调 super().__init__()，这些继承方法访问
    self._client 会抛 AttributeError；框架对能力方法均有 getattr 守卫，
    纯鸭子类型包装（只暴露 invoke/stream）即可安全接入。
    """

    def __init__(self, model_client_config, model_config, *, label: str) -> None:
        self._model_client_config = model_client_config
        self._model_config = model_config
        self._log_label = label
        self._delegate: Model | None = None

    def _get_delegate(self) -> Model:
        if self._delegate is None:
            self._delegate = Model(
                model_client_config=self._model_client_config,
                model_config=self._model_config,
            )
        return self._delegate

    async def invoke(self, messages, **kwargs):
        run_id = uuid4().hex[:8]
        logger.info("[LLM] 输入 %s run=%s messages=%s",
                    self._log_label, run_id, serialize_messages(messages))
        t0 = time.perf_counter()
        try:
            response = await self._get_delegate().invoke(messages, **kwargs)
        except Exception:
            logger.warning("[LLM] 调用异常 %s run=%s", self._log_label, run_id)
            raise
        logger.info("[LLM] 返回 %s run=%s 耗时=%.2fs 输出字符=%d",
                    self._log_label, run_id, time.perf_counter() - t0,
                    len(getattr(response, "content", "") or ""))
        return response

    async def stream(self, messages, **kwargs):
        run_id = uuid4().hex[:8]
        logger.info("[LLM] 输入 %s run=%s messages=%s",
                    self._log_label, run_id, serialize_messages(messages))
        async for chunk in self._get_delegate().stream(messages, **kwargs):
            yield chunk


class GuardedModel:
    """openjiuwen Model 的薄 wrapper：预算守卫 + io 日志 + 用量落库（行为对齐旧 TokenBudgetChatOpenAI+LLMIOCharLogger）。"""

    def __init__(self, model: Model, *, model_name: str, context_limit: int,
                 output_reserve: int, label: str,
                 llm_timeout_seconds: int | float | None = None) -> None:
        self._model = model
        self._model_name = model_name
        # 避免统一预留值吃满小上下文模型（对齐旧 configure_token_budget 语义）
        max_default_reserve = max(context_limit // 4, 1)
        self._output_reserve = max(min(int(output_reserve), max_default_reserve), 0)
        self._context_limit = max(int(context_limit), 1)
        self._label = label
        self._llm_timeout_seconds = llm_timeout_seconds

    async def invoke(self, messages, **kwargs):
        """调用底层 Model；``timeout`` 等 kwargs 原样透传。

        用实例配置超时做 setdefault 兜底；调用方显式传 timeout 仍优先。
        """
        if self._llm_timeout_seconds is not None:
            kwargs.setdefault("timeout", self._llm_timeout_seconds)
        run_id = uuid4().hex
        msg_list = messages if isinstance(messages, list) else [messages]
        estimated = estimate_model_request_tokens(msg_list, kwargs)
        output_reserve = max(self._output_reserve, int(kwargs.get("max_tokens") or 0))
        logger.info("[LLM] Token预算 model=%s estimated_input=%d output_reserve=%d max_tokens=%d",
                    self._model_name, estimated, output_reserve, self._context_limit)
        if estimated + output_reserve > self._context_limit:
            logger.warning("[LLM] 请求超过模型上下文，已阻止调用: model=%s estimated_input=%d", self._model_name, estimated)
            raise ModelContextLengthExceeded(
                model=self._model_name, estimated_input=estimated,
                output_reserve=output_reserve, limit=self._context_limit)
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        t0 = time.perf_counter()
        logger.info("[LLM] 请求 %s run=%s", self._label, run_id[:8])
        logger.info("[LLM] 输入 %s run=%s messages=%s",
                    self._label, run_id[:8], serialize_messages(messages))
        try:
            response = await self._model.invoke(messages, **kwargs)
        except Exception as exc:
            await self._persist_usage_async(run_id, started_at, t0, 0, "FAILED")
            # openjiuwen 把供应商异常包成 FrameworkError，原始异常在 __cause__ 链上
            if any(is_provider_context_limit_error(cause) for cause in _iter_causes(exc)):
                raise ModelContextLengthExceeded(
                    model=self._model_name, estimated_input=estimated,
                    output_reserve=output_reserve, limit=self._context_limit) from exc
            raise
        usage = getattr(response, "usage_metadata", None) or {}
        # usage_metadata 两种形态：dict（旧假对象/部分适配）或 openjiuwen 自定义对象
        token_cost = int(usage.get("total_tokens") or 0) if isinstance(usage, dict) else int(getattr(usage, "total_tokens", 0) or 0)
        logger.info("[LLM] 返回 %s run=%s 输出字符=%d Token=%d",
                    self._label, run_id[:8], len(getattr(response, "content", "") or ""), token_cost)
        await self._persist_usage_async(run_id, started_at, t0, token_cost, "SUCCESS")
        return response

    async def _persist_usage_async(self, run_id: str, started_at, t0: float, token_cost: int, status: str) -> None:
        """同步 SQLite 写放到工作线程，避免与 pipeline 线程写同一库文件时
        busy-timeout 阻塞事件循环。"""
        await asyncio.to_thread(self._persist_usage, run_id, started_at, t0, token_cost, status)

    def _persist_usage(self, run_id: str, started_at, t0: float, token_cost: int, status: str) -> None:
        try:
            from src.infrastructure.db.models import LlmTokenUsageLog

            with SessionLocal() as db:
                db.add(LlmTokenUsageLog(
                    etl_dt=started_at.date(), id=run_id, start_time=started_at,
                    time_spent=max(round((time.perf_counter() - t0) * 1000), 0),
                    token_cost=max(int(token_cost or 0), 0), exec_status=status,
                ))
                db.commit()
        except Exception:
            logger.exception("[LLM] 调用统计写入失败 run=%s", run_id[:8])


def resolve_temperature(settings, role: str) -> float:
    """角色温度解析：{ROLE}_LLM_TEMPERATURE（>=0 视为已配置）优先，回退全局 LLM_TEMPERATURE。"""
    role_temp = float(getattr(settings, f"{role}_llm_temperature", -1.0))
    return role_temp if role_temp >= 0 else float(getattr(settings, "llm_temperature", 0.1))


def get_model(role: str = "report_generation", temperature: float | None = None,
              use_cache: bool = True) -> GuardedModel:
    settings = get_settings()
    api_key = getattr(settings, f"{role}_llm_api_key", "") or settings.llm_api_key
    base_url = getattr(settings, f"{role}_llm_base_url", "") or settings.llm_base_url
    model = getattr(settings, f"{role}_llm_model", "") or settings.llm_model
    role_model = getattr(settings, f"{role}_llm_model", "")
    context_limit = int(getattr(settings, f"{role}_llm_max_tokens", 0) or settings.llm_max_tokens) if role_model else int(settings.llm_max_tokens)
    # 显式传参优先（个别调用点需要偏离配置时仍可用），缺省走配置文件
    if temperature is None:
        temperature = resolve_temperature(settings, role)

    cache_key = f"{role}:{temperature}"
    if use_cache and cache_key in _model_cache:
        return _model_cache[cache_key]

    client_cfg = ModelClientConfig(
        client_provider="OpenAI", api_key=api_key, api_base=base_url,
        # 独立客户端避免报告线程关闭事件循环后污染主对话；超时也可逐请求覆盖
        timeout=settings.llm_timeout_seconds,
        # SDK 默认 3 次重试会把 429 限流放大成最多 4 倍实际请求，显式压低
        max_retries=settings.llm_max_retries,
        use_shared_llm_http_client=False,
        verify_ssl=settings.llm_verify_ssl,
    )
    request_cfg = ModelRequestConfig(model_name=model, temperature=temperature)
    guarded = GuardedModel(
        Model(client_cfg, request_cfg),
        model_name=model, context_limit=context_limit,
        output_reserve=settings.llm_output_token_reserve,
        label=f"{role}/{model}",
        llm_timeout_seconds=settings.llm_timeout_seconds,
    )
    if use_cache:
        _model_cache[cache_key] = guarded
    return guarded
