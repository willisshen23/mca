from __future__ import annotations

from src.infrastructure.integrations.bank_marketing.schemas import ApiResult
from src.infrastructure.tools import call_function


def fetch_activity_list(params: dict) -> ApiResult:
    return call_function("get_activity_list", params)


def fetch_data_template_list(params: dict) -> ApiResult:
    return call_function("get_template_list", params)


def fetch_component_values(params: dict) -> ApiResult:
    return call_function("get_component_values", params)


def fetch_outbound_activity_data(params: dict) -> ApiResult:
    return call_function("get_outbound_activity_data", params)
