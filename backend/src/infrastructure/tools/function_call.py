from __future__ import annotations

import logging
import time
from typing import Callable

from src.infrastructure.integrations.bank_marketing import ApiResult, BankMarketingApiClient

logger = logging.getLogger("njbank.agent")

_client = BankMarketingApiClient()

FUNCTION_REGISTRY: dict[str, Callable[[dict], ApiResult]] = {
    "get_activity_list": _client.get_activity_list,
    "get_template_list": _client.get_template_list,
    "get_component_values": _client.get_component_values,
    "get_outbound_activity_data": _client.get_outbound_activity_data,
}


def call_function(name: str, params: dict | None = None) -> ApiResult:
    params = params or {}
    function = FUNCTION_REGISTRY.get(name)
    if function is None:
        logger.error("Function Call工具不存 %s", name)
        return ApiResult(success=False, error=f"未知工具: {name}")

    started = time.perf_counter()
    logger.info("Function Call开 %s params=%s", name, params)
    result = function(params)
    logger.info(
        "Function Call完成: %s success=%s cost_ms=%.2f",
        name,
        result.success,
        (time.perf_counter() - started) * 1000,
    )
    return result
