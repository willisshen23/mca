from __future__ import annotations

import json
import logging
import math
from typing import Any

MODEL_BUSY_MESSAGE = "系统正忙，请稍后重试"

logger = logging.getLogger("njbank.agent")

# tiktoken 首次 get_encoding 需联网下载 BPE 词表；离线/内网部署时该请求
# 会同步阻塞到 TCP 超时（约 1 分钟），在事件循环线程上调用会冻结整个服务。
# 因此只尝试一次：成功则进程内缓存，失败则永久回退字符估算，不再重复联网。
_tiktoken_encoding: Any = None
_tiktoken_unavailable = False


def _get_tiktoken_encoding() -> Any:
    global _tiktoken_encoding, _tiktoken_unavailable
    if _tiktoken_encoding is not None or _tiktoken_unavailable:
        return _tiktoken_encoding
    try:
        import tiktoken

        _tiktoken_encoding = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _tiktoken_unavailable = True
        logger.warning(
            "tiktoken cl100k_base 加载失败（疑似离线环境无法下载词表），"
            "后续 token 估算全部退化为字符估算",
            exc_info=True,
        )
    return _tiktoken_encoding


def warm_token_estimator() -> None:
    """预热 token 估算器（触发一次性 tiktoken 词表加载）。

    可能在离线环境下阻塞到网络超时，调用方须放在工作线程中执行
    （如 lifespan 里 asyncio.to_thread），切勿在事件循环线程直接调用。
    """
    _get_tiktoken_encoding()


class ModelContextLengthExceeded(RuntimeError):
    """模型请求超过其已配置的上下文容量。"""

    def __init__(self, *, model: str, estimated_input: int, output_reserve: int, limit: int) -> None:
        super().__init__(MODEL_BUSY_MESSAGE)
        self.model = model
        self.estimated_input = estimated_input
        self.output_reserve = output_reserve
        self.limit = limit


def estimate_text_tokens(text: str) -> int:
    """估算文本 Token 数；Tokenizer 不可用时采用保守字符估算。"""
    if not text:
        return 0
    encoding = _get_tiktoken_encoding()
    if encoding is not None:
        try:
            return len(encoding.encode(text))
        except Exception:
            pass
    non_ascii = sum(1 for char in text if ord(char) > 127)
    ascii_chars = len(text) - non_ascii
    return non_ascii + math.ceil(ascii_chars / 4)


def estimate_model_request_tokens(messages: list[Any], options: dict[str, Any] | None = None) -> int:
    """估算一次模型请求的输入，包括消息正文和工具/响应格式定义。"""
    message_payload = []
    for message in messages or []:
        if hasattr(message, "model_dump"):
            message_payload.append(message.model_dump())
        elif isinstance(message, dict):
            message_payload.append(message)
        else:
            message_payload.append(str(message))
    prompt_options = {
        key: value
        for key, value in (options or {}).items()
        if key in {"tools", "tool_choice", "functions", "function_call", "response_format"}
    }
    serialized = json.dumps(
        {"messages": message_payload, "options": prompt_options},
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    return estimate_text_tokens(serialized)


def is_provider_context_limit_error(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    type_name = f"{type(exc).__module__}.{type(exc).__name__}".lower()
    message = str(exc).lower()
    markers = {
        "context_length_exceeded",
        "maximum context length",
        "context window",
        "context length",
        "max context",
        "token limit",
        "too many tokens",
        "prompt is too long",
        "input is too long",
        "input length",
        "上下文长度",
        "上下文窗口",
        "token数量超过",
        "token 数量超过",
    }
    return "contextlengthexceeded" in type_name or any(marker in message for marker in markers)
