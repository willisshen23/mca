"""API2 mock endpoints for outbound activity data service documents."""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Body
from fastapi.encoders import jsonable_encoder

try:
    from .waihu_data_service import get_activities_by_ids
except ImportError:
    from waihu_data_service import get_activities_by_ids

logger = logging.getLogger("mock.outbound_api2")

router = APIRouter(tags=["api2-outbound-activity"])


TRADE_CODE_ALIASES = {
    "EDW_RTL_MED_ASSET_CONVERSION": "asset_conversion",
    "EDW_RTL_MED_PRODUCT_TRANSACTION": "product_transaction",
    "EDW_RTL_MED_ACTIVITY_BASE_INFO": "activity_base_info",
    "EDW_RTL_MED_OUTBOUND_CALL_EXECUTION": "outbound_call_execution",
    "EDW_RTL_MED_OUTBOUND_CALL_EXECU": "outbound_call_execution",
    "EDW_RTL_MED_SOURCE_OF_PRODUCT_VALIDCALL": "source_of_product_validcall",
    "EDW_RTL_MED_SOURCE_OF_PRODUCT_V": "source_of_product_validcall",
}

ASSET_CONVERSION_FIELDS = {
    "客群范围": "customer_segment",
    "act_no": "act_no",
    "act_name": "act_name",
    "外呼人数": "total_call_count",
    "外呼3日后金融资产提升人数": "aum_increase_3d",
    "外呼7日后金融资产提升人数": "aum_increase_7d",
    "外呼3日后活期余额提升人数": "current_increase_3d",
    "外呼7日后活期余额提升人数": "current_increase_7d",
    "外呼3日后定存余额提升人数": "fixed_increase_3d",
    "外呼7日后定存余额提升人数": "fixed_increase_7d",
    "外呼3日后理财余额提升人数": "fin_increase_3d",
    "外呼7日后理财余额提升人数": "fin_increase_7d",
    "外呼3日后金融资产提升": "aum_increase_amt_3d",
    "外呼7日后金融资产提升": "aum_increase_amt_7d",
    "外呼3日后活期余额提升": "current_increase_amt_3d",
    "外呼7日后活期余额提升": "current_increase_amt_7d",
    "外呼3日后定存余额提升": "fixed_increase_amt_3d",
    "外呼7日后定存余额提升": "fixed_increase_amt_7d",
    "外呼3日后理财余额提升": "fin_increase_amt_3d",
    "外呼7日后理财余额提升": "fin_increase_amt_7d",
    "外呼3日后人均金融资产提升": "avg_aum_increase_amt_3d",
    "外呼7日后人均金融资产提升": "avg_aum_increase_amt_7d",
    "外呼3日后人均活期余额提升": "avg_current_increase_amt_3d",
    "外呼7日后人均活期余额提升": "avg_current_increase_amt_7d",
    "外呼3日后人均定存余额提升": "avg_fixed_increase_amt_3d",
    "外呼7日后人均定存余额提升": "avg_fixed_increase_amt_7d",
    "外呼3日后人均理财余额提升": "avg_fin_increase_amt_3d",
    "外呼7日后人均理财余额提升": "avg_fin_increase_amt_7d",
}

PRODUCT_TRANSACTION_FIELDS = {
    "客群范围": "customer_segment",
    "act_no": "act_no",
    "act_name": "act_name",
    "外呼人数": "total_count",
    "联系失败人数": "total_count",
    "有效通话人数": "total_count",
    "外呼7日内点击理财人数": "fin_click_7d",
    "外呼7日内购买理财人数": "fin_buy_7d",
    "外呼7日内购买理财金额": "fin_buy_amt_7d",
    "外呼7日内购买理财金额大于100万人数": "fin_buy_over_1w_7d",
    "外呼7日内购买理财金额大于100万金额": "fin_buy_over_1w_amt_7d",
    "外呼7日内点击存款人数": "dpsit_click_7d",
    "外呼7日内购买存款人数": "dpsit_buy_7d",
    "外呼7日内购买存款金额": "dpsit_buy_amt_7d",
    "外呼7日内购买存款金额大于100万人数": "dpsit_buy_over_1w_7d",
    "外呼7日内购买存款金额大于100万金额": "dpsit_buy_over_1w_amt_7d",
}

ACTIVITY_BASE_FIELDS = {
    "act_no": "act_no",
    "act_name": "act_name",
    "活动开始时间": "execute_start_time",
    "活动结束时间": "execute_end_time",
    "活动状态": "status",
    "创建人名称": "act_initiator_name",
    "创建机构名称": "act_initiator_org_name",
    "act_type": "act_type",
    "活动说明": "act_desc",
    "yewu_type": "business_type",
}

OUTBOUND_EXECUTION_FIELDS = {
    "act_no": "act_no",
    "act_name": "act_name",
    "yewu_type": "business_type",
    "外呼执行天数": "call_days",
    "外呼人数": "total_call_count",
    "外呼成功人数": "success_call_count",
    "上午外呼成功人数": "morning_success_count",
    "下午外呼成功人数": "afternoon_success_count",
    "外呼失败人数": "fail_call_count",
    "上午外呼失败人数": "morning_fail_count",
    "下午外呼失败人数": "afternoon_fail_count",
    "外呼成功平均通话时间": "avg_success_call_duration",
    "有效通话人数": "valid_call_count",
    "上午有效通话人数": "morning_valid_count",
    "下午有效通话人数": "afternoon_valid_count",
    "无效通话人数": "invalid_call_count",
    "感兴趣人数": "interested_count",
    "待定人数": "undecided_count",
    "不感兴趣人数": "not_interested_count",
    "黑名单人数": "blacklist_count",
}

SOURCE_OF_PRODUCT_FIELDS = {
    "act_no": "act_no",
    "act_name": "act_name",
    "客群范围": "customer_segment",
    "购买存款人数": "buy_count",
    "购买理财人数": "buy_count",
    "新资金引入人数": "new_fund_count",
    "资金流失人数": "fund_outflow",
    "活期转存人数": "current_transfer",
    "产品搬家人数": "product_transfer",
}


@router.post("/dataservice/query/{trade_code}")
async def api_query_outbound_data_post(trade_code: str, body: dict[str, Any] | None = Body(default=None)):
    return _query_outbound_data(trade_code, body or {})


@router.get("/dataservice/query/{trade_code}")
async def api_query_outbound_data_get(
    trade_code: str,
    edw_act_no: str = "",
    act_no: str = "",
    activity_id: str = "",
    edw_start_dt: str = "",
    edw_end_dt: str = "",
    edw_customer_segment: str = "",
    edw_product_type: str = "",
    limit: int = 20,
    start: int = 1,
):
    body = {
        "pms": {
            "edw_act_no": edw_act_no or act_no or activity_id,
            "edw_start_dt": edw_start_dt,
            "edw_end_dt": edw_end_dt,
            "edw_customer_segment": edw_customer_segment,
            "edw_product_type": edw_product_type,
        },
        "props": {"limit": limit, "start": start},
    }
    return _query_outbound_data(trade_code, body)


def _query_outbound_data(trade_code: str, body: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    normalized_trade_code = trade_code.upper().strip()
    api_key = TRADE_CODE_ALIASES.get(normalized_trade_code)
    act_nos = _extract_act_nos(body)
    records = get_activities_by_ids(act_nos) if act_nos else {}
    rows: list[dict[str, Any]] = []
    if api_key:
        for act_no in act_nos:
            record = records.get(act_no)
            if record:
                rows.extend(_build_rows_for_record(api_key, record))
        rows = _filter_rows(rows, body)
    logger.info(
        "api2_outbound_query trade_code=%s act_nos=%s matched=%d rows=%d cost_ms=%.2f",
        normalized_trade_code,
        act_nos,
        len(records),
        len(rows),
        (time.perf_counter() - started) * 1000,
    )
    if not api_key:
        return _response([], ret_code="404", ret_msg=f"Unsupported trade_code: {trade_code}")
    return _response(rows)


def _extract_act_nos(body: dict[str, Any]) -> list[str]:
    pms = body.get("pms") if isinstance(body.get("pms"), dict) else {}
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    activity = body.get("activity") if isinstance(body.get("activity"), dict) else {}
    value = (
        pms.get("edw_act_no")
        or params.get("edw_act_no")
        or body.get("edw_act_no")
        or body.get("act_no")
        or body.get("actNo")
        or body.get("activity_id")
        or activity.get("act_no")
        or activity.get("actNo")
        or activity.get("activity_id")
        or activity.get("活动编号")
        or ""
    )
    return _split_act_nos(value)


def _split_act_nos(value: Any) -> list[str]:
    """解析 edw_act_no：兼容单值 A、多值 A','B','C、带首尾引号 'A','B','C' 及 list。"""
    if isinstance(value, (list, tuple)):
        items = [str(item) for item in value]
    else:
        items = str(value).split("','")
    act_nos: list[str] = []
    for item in items:
        text = item.strip().strip("'").strip()
        if text and text not in act_nos:
            act_nos.append(text)
    return act_nos


def _build_rows_for_record(api_key: str | None, record: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not api_key or not record:
        return []
    if api_key == "asset_conversion":
        rows = [
            record.get("all_customers_fund_conversion"),
            record.get("success_customers_fund_conversion"),
            record.get("failed_customers_fund_conversion"),
            record.get("effective_call_fund_conversion"),
        ]
        return [_translate(row, ASSET_CONVERSION_FIELDS) for row in rows]
    if api_key == "product_transaction":
        rows = [
            record.get("all_customers_prodtxn"),
            record.get("failed_customers_prodtxn"),
            record.get("success_customers_prodtxn"),
            record.get("effective_call_customers_prodtxn"),
        ]
        return [_translate(row, PRODUCT_TRANSACTION_FIELDS) for row in rows]
    if api_key == "activity_base_info":
        return [_translate(record.get("basic_info"), ACTIVITY_BASE_FIELDS)]
    if api_key == "outbound_call_execution":
        return [_translate(record.get("execution"), OUTBOUND_EXECUTION_FIELDS)]
    if api_key == "source_of_product_validcall":
        deposit = _translate(record.get("effective_call_deposit_source"), SOURCE_OF_PRODUCT_FIELDS)
        wealth = _translate(record.get("effective_call_wealth_source"), SOURCE_OF_PRODUCT_FIELDS)
        if deposit:
            deposit["product_type"] = "存款"
        if wealth:
            wealth["product_type"] = "理财"
        return [deposit, wealth]
    return []


def _filter_rows(rows: list[dict[str, Any]], body: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in rows if _has_business_data(row)]
    pms = body.get("pms") if isinstance(body.get("pms"), dict) else {}
    customer_segment = str(pms.get("edw_customer_segment") or body.get("edw_customer_segment") or "").strip()
    product_type = str(pms.get("edw_product_type") or body.get("edw_product_type") or "").strip()
    if customer_segment:
        rows = [row for row in rows if str(row.get("customer_segment") or "") == customer_segment]
    if product_type:
        rows = [row for row in rows if str(row.get("product_type") or "") == product_type]
    props = body.get("props") if isinstance(body.get("props"), dict) else {}
    start = _to_int(props.get("start") or body.get("start"), 1)
    limit = _to_int(props.get("limit") or body.get("limit"), 20)
    offset = max(start - 1, 0) * max(limit, 1)
    return rows[offset : offset + max(limit, 1)]


def _translate(row: dict[str, Any] | None, mapping: dict[str, str]) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    translated: dict[str, Any] = {}
    for source_key, target_key in mapping.items():
        if source_key in row and row[source_key] is not None:
            translated[target_key] = row[source_key]
    return translated


def _has_business_data(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    for key, value in row.items():
        if key in {"act_no", "act_name", "customer_segment", "product_type", "business_type", "status"}:
            continue
        if value not in ("", None, [], {}):
            return True
    return False


def _response(rows: list[dict[str, Any]], ret_code: str = "000000", ret_msg: str = "success") -> dict[str, Any]:
    rows = [row for row in rows if isinstance(row, dict)]
    return jsonable_encoder(
        {
            "retCode": ret_code,
            "retMsg": ret_msg,
            "totalCount": len(rows),
            "result": rows,
        }
    )


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
