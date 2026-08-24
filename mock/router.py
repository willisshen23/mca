"""FastAPI router for marketing campaign mock API."""
from __future__ import annotations

import copy
import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field

try:
    from .data_service import get_campaign_by_id, load_data, reload_data
    from .schemas import Campaign, CampaignSearchResponse
except ImportError:
    from data_service import get_campaign_by_id, load_data, reload_data
    from schemas import Campaign, CampaignSearchResponse

logger = logging.getLogger("mock.campaign")

router = APIRouter(tags=["campaigns"])

_BASE_DIR = Path(__file__).parent
_TEMPLATE_SAMPLE_PATH = _BASE_DIR / "获取分析模板列表api" / "获取分析模板列表api-返回报文结构"
_ACTIVITY_SAMPLE_PATH = _BASE_DIR / "通过活动关键词查询活动信息api" / "通过活动关键词查询活动信息api-返回报文结构"
_TEMPLATE_DETAIL_SAMPLE_PATH = (
    _BASE_DIR
    / "通过分析模板 id 、活动 id、时间范围获取分析模板详情及活动数据api"
    / "通过分析模板 id 、活动 id、时间范围获取分析模板详情及活动数据api-返回报文结构"
)

_SAMPLE_ACTIVITY_NAMES = {
    "PV10175522026060222378": "演示银行App6月促活营销",
    "PV10175522026042922263": "五一节前理财营销",
}


class TemplateListRequest(BaseModel):
    """Request body for 获取分析模板列表api."""

    model_config = ConfigDict(extra="allow")

    page_num: int = Field(default=1, alias="pageNum", ge=1)
    page_size: int = Field(default=999, alias="pageSize", ge=1)
    type_cd: str = Field(default="", alias="typeCd")
    proj_name: str = Field(default="", alias="projName")
    proj_status_cd: str = Field(default="", alias="projStatusCd")
    origin_type_cd: str = Field(default="", alias="originTypeCd")
    order_type: str = Field(default="2", alias="orderType")
    proj_type_no: str = Field(default="", alias="projTypeNo")
    proj_type_pid_no: str = Field(default="", alias="projTypePidNo")
    is_new_version: str = Field(default="1", alias="isNewVersion")


class ActivitySearchRequest(BaseModel):
    """Request body for 通过活动关键词查询活动信息api."""

    model_config = ConfigDict(extra="allow")

    page_size: int = Field(default=999, alias="pageSize", ge=1)
    page_num: int = Field(default=1, alias="pageNum", ge=1)
    date_value: str | None = Field(default=None, alias="date")
    act_status_cd: str = Field(default="", alias="actStatusCd")
    sgin_act: str = Field(default="", alias="sginAct")
    act_src_cd: str = Field(default="", alias="actSrcCd")
    act_type_cd: str = Field(default="", alias="actTypeCd")
    act_no: str = Field(default="", alias="actNo")
    label_no_list: list[str] = Field(default_factory=list, alias="labelNoList")
    act_name: str = Field(default="", alias="actName")
    act_start_dt: str = Field(default="", alias="actStartDt")
    act_end_dt: str = Field(default="", alias="actEndDt")
    show_mall_act: int = Field(default=0, alias="showMallAct")
    creator_no: str = Field(default="", alias="creatorNo")
    channel: str = Field(default="", description="活动渠道，如外呼、短信")


class TemplateDetailRequest(BaseModel):
    """Request body for 通过分析模板 id、活动 id、时间范围获取详情及活动数据api."""

    model_config = ConfigDict(extra="allow")

    proj_no: str = Field(default="", alias="projNo")
    etl_dt_start: str = Field(default="", alias="etlDtStart")
    etl_dt_end: str = Field(default="", alias="etlDtEnd")
    act_nos: list[str] = Field(default_factory=list, alias="actNos")

    # Backward-compatible aliases used by the old mock endpoint.
    template_id: str = ""
    activity_ids: list[str] = Field(default_factory=list)
    component_ids: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)


class OutboundActivityDataRequest(BaseModel):
    activity_id: str = Field(default="")
    activity: dict = Field(default_factory=dict)


@router.get("/campaigns/search")
async def api_search_campaigns_get(
    q: str = Query(default="", description="活动名称/编号模糊查询关键词"),
    limit: int = Query(default=50, ge=1, le=999, description="返回条数上限"),
):
    """通过活动关键词查询活动信息.

    GET 形式兼容旧配置；返回字段按照 `通过活动关键词查询活动信息api` 样例组织。
    """
    body = ActivitySearchRequest(pageSize=limit, pageNum=1, actNo=q, actName=q)
    return _search_activity_payload(body)


@router.post("/campaigns/search")
async def api_search_campaigns_post(body: ActivitySearchRequest | None = Body(default=None)):
    """通过活动关键词查询活动信息.

    支持样例请求体中的 `actNo`/`actName` 关键词与分页参数。
    """
    return _search_activity_payload(body or ActivitySearchRequest())


@router.get("/campaigns", response_model=CampaignSearchResponse)
async def api_list_campaigns(
    limit: int = Query(default=50, ge=1, le=200, description="返回条数上限"),
    offset: int = Query(default=0, ge=0, description="偏移量"),
):
    """列出所有活动，保留原 mock 调试接口."""
    started = time.perf_counter()
    records = load_data()
    total = len(records)
    records = records[offset : offset + limit]

    campaigns = [Campaign(**record).model_dump(by_alias=True) for record in records]

    logger.info(
        "campaign_list total=%d offset=%d limit=%d returned=%d cost_ms=%.2f",
        total,
        offset,
        limit,
        len(campaigns),
        (time.perf_counter() - started) * 1000,
    )
    return {"total": total, "campaigns": campaigns}


@router.get("/campaigns/{activity_id}")
async def api_get_campaign(activity_id: str):
    """根据活动编号精确查询单个活动详情，保留原 mock 调试接口."""
    started = time.perf_counter()
    record = get_campaign_by_id(activity_id)
    if record is None:
        logger.warning("campaign_get not_found activity_id=%s", activity_id)
        raise HTTPException(status_code=404, detail="活动不存在")

    campaign = Campaign(**record).model_dump(by_alias=True)
    logger.info(
        "campaign_get activity_id=%s cost_ms=%.2f",
        activity_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"campaign": campaign}


@router.post("/campaigns/reload")
async def api_reload_campaigns():
    """强制重新加载 Excel 数据（开发调试用）."""
    started = time.perf_counter()
    records = reload_data()
    logger.info(
        "campaign_reload count=%d cost_ms=%.2f",
        len(records),
        (time.perf_counter() - started) * 1000,
    )
    return {"status": "reloaded", "count": len(records)}


@router.get("/templates")
async def api_list_templates_get(
    pageNum: int = Query(default=1, ge=1),
    pageSize: int = Query(default=999, ge=1),
    typeCd: str = Query(default="1"),
    projName: str = Query(default=""),
    projStatusCd: str = Query(default=""),
    originTypeCd: str = Query(default=""),
    orderType: str = Query(default="2"),
    projTypeNo: str = Query(default=""),
    projTypePidNo: str = Query(default=""),
    isNewVersion: str = Query(default="1"),
):
    """获取分析模板列表.

    GET 形式兼容旧配置；返回字段按照 `获取分析模板列表api` 样例组织。
    """
    body = TemplateListRequest(
        pageNum=pageNum,
        pageSize=pageSize,
        typeCd=typeCd,
        projName=projName,
        projStatusCd=projStatusCd,
        originTypeCd=originTypeCd,
        orderType=orderType,
        projTypeNo=projTypeNo,
        projTypePidNo=projTypePidNo,
        isNewVersion=isNewVersion,
    )
    return _template_list_payload(body)


@router.post("/templates")
async def api_list_templates_post(body: TemplateListRequest | None = Body(default=None)):
    """获取分析模板列表，支持样例请求体."""
    return _template_list_payload(body or TemplateListRequest())


@router.post("/component-values")
async def api_template_detail_and_activity_data(body: TemplateDetailRequest):
    """通过分析模板 id、活动 id、时间范围获取分析模板详情及活动数据."""
    started = time.perf_counter()
    proj_no = body.proj_no or body.template_id
    act_nos = body.act_nos or body.activity_ids
    payload = _build_template_detail_payload(
        proj_no=proj_no,
        act_nos=act_nos,
        etl_dt_start=body.etl_dt_start,
        etl_dt_end=body.etl_dt_end,
    )
    logger.info(
        "template_detail proj_no=%s activities=%d plates=%d cost_ms=%.2f",
        proj_no,
        len(act_nos),
        len(payload),
        (time.perf_counter() - started) * 1000,
    )
    return payload


@router.post("/outbound-activity-data")
async def api_outbound_activity_data(body: OutboundActivityDataRequest):
    """Return mock business metrics for a selected outbound activity."""
    started = time.perf_counter()
    activity_id = body.activity_id or str(body.activity.get("activity_id") or body.activity.get("活动编号") or "")
    record = get_campaign_by_id(activity_id) if activity_id else None
    if record is None:
        logger.info(
            "outbound_activity_data activity_id=%s matched=false cost_ms=%.2f",
            activity_id,
            (time.perf_counter() - started) * 1000,
        )
        return {
            "matched": False,
            "activity_id": activity_id,
            "message": "No outbound business data matched this activity.",
        }

    business_data = {
        "activity_id": activity_id,
        "activity_name": record.get("活动名称", ""),
        "activity_period": {
            "start_date": _format_date(record.get("活动开始日期")),
            "end_date": _format_date(record.get("活动结束日期")),
        },
        "outbound_summary": {
            "touch_count": int(_sum_number([record], "活动运营人数")),
            "valuable_customers": int(_sum_number([record], "价值客户数")),
            "converted_valuable_customers": int(_sum_number([record], "转化价值客户数")),
            "lost_valuable_customers": int(_sum_number([record], "流失价值客户数")),
        },
        "asset_lift": {
            "financial_asset_increase": _sum_number([record], "金融资产提升额"),
            "deposit_increase": _sum_number([record], "存款提升额"),
            "wealth_increase": _sum_number([record], "理财提升额"),
        },
        "baseline_metrics": {
            "last_month_aum": record.get("上月末AUM时点值"),
            "last_month_wealth": record.get("上个月理财余额"),
        },
        "source": "mock_outbound_activity_data",
    }
    logger.info(
        "outbound_activity_data activity_id=%s matched=true cost_ms=%.2f",
        activity_id,
        (time.perf_counter() - started) * 1000,
    )
    return {"matched": True, "data": business_data}


def _template_list_payload(body: TemplateListRequest) -> list[dict[str, Any]]:
    started = time.perf_counter()
    records = _load_json_rows(_TEMPLATE_SAMPLE_PATH)
    filtered = _filter_templates(records, body)
    paginated = _paginate(filtered, body.page_num, body.page_size)
    logger.info(
        "template_list sample_file=%s rows=%d matched=%d returned=%d cost_ms=%.2f",
        _TEMPLATE_SAMPLE_PATH.name,
        len(records),
        len(filtered),
        len(paginated),
        (time.perf_counter() - started) * 1000,
    )
    return jsonable_encoder(paginated)


def _search_activity_payload(body: ActivitySearchRequest) -> list[dict[str, Any]]:
    started = time.perf_counter()
    rows = _load_json_rows(_ACTIVITY_SAMPLE_PATH)
    # Merge campaign records from the Excel data source so newly added
    # activities are searchable without editing the sample file.
    # _filter_activities dedups by act_no, keeping the sample row first.
    rows.extend(_campaigns_to_activity_rows(load_data()))
    filtered = _filter_activities(rows, body)
    paginated = _paginate(filtered, body.page_num, body.page_size)
    logger.info(
        "campaign_keyword_search keyword=%r sample_file=%s rows=%d matched=%d returned=%d cost_ms=%.2f",
        _activity_keyword(body),
        _ACTIVITY_SAMPLE_PATH.name,
        len(rows),
        len(filtered),
        len(paginated),
        (time.perf_counter() - started) * 1000,
    )
    return jsonable_encoder(paginated)


def _build_template_detail_payload(
    proj_no: str,
    act_nos: list[str],
    etl_dt_start: str,
    etl_dt_end: str,
) -> list[dict[str, Any]]:
    plates = _load_json_like_rows(_TEMPLATE_DETAIL_SAMPLE_PATH)
    _inject_campaign_values(plates, act_nos)
    _rewrite_multi_activity_plates(plates, act_nos)
    return plates


def _rewrite_multi_activity_plates(plates: list[dict[str, Any]], act_nos: list[str]) -> None:
    """Rewrite multi-activity comparison plates to reference the requested campaigns.

    The sample response file hardcodes two demo activities in its multi-activity
    plates (plateTypeCd == "4"). Replace those plates' indicators with rows built
    from the requested actNos, using real campaign names from the Excel data
    source so generated reports never show the demo activities.
    """
    if not act_nos:
        return
    records = _select_campaign_records(act_nos)
    activities = _resolve_activity_refs([str(act_no) for act_no in act_nos], records)
    for plate in plates:
        if str(plate.get("plateTypeCd") or "") != "4":
            continue
        if isinstance(plate.get("plateShowIndCfgInfDtoList"), list):
            plate["plateShowIndCfgInfDtoList"] = copy.deepcopy(
                _multi_activity_indicators(activities, records)
            )


def _inject_campaign_values(plates: list[dict[str, Any]], act_nos: list[str]) -> None:
    """Replace stub 0 values in template detail sample with actual campaign data.

    Scans all plates' indicators and replaces resData with real campaign
    metrics for the fields: 上月末AUM时点值 (I200209) and 上个月理财余额 (I200170).
    """
    if not act_nos:
        return
    records = _select_campaign_records(act_nos)
    if not records:
        return
    campaign = records[0]

    # Map indicator indexNo -> campaign record key
    field_map: dict[str, str] = {
        "I200170": "上个月理财余额",
        "I200209": "上月末AUM时点值",
    }

    for plate in plates:
        indicators = plate.get("plateShowIndCfgInfDtoList") or []
        for indicator in indicators:
            if not isinstance(indicator, dict):
                continue
            index_no = str(indicator.get("indexNo") or "")
            campaign_key = field_map.get(index_no)
            if not campaign_key:
                continue
            value = campaign.get(campaign_key)
            if value is None:
                continue
            indicator["resData"] = [{index_no: value}]


def _load_json_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Failed to parse sample JSON %s: %s", path.name, exc)
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return [row for row in payload["rows"] if isinstance(row, dict)]
    return []


def _load_json_like_rows(path: Path) -> list[dict[str, Any]]:
    """Load sample response files that contain inline Chinese comments.

    The template detail sample is intentionally written as annotated JSON-like
    documentation. The mock endpoint still needs to return JSON, so this loader
    removes documentation comments at read time without changing the source file.
    """
    if not path.exists():
        logger.warning("Sample response file not found: %s", path)
        return []

    cleaned = "\n".join(
        _strip_json_like_comment(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ).strip()
    if not cleaned:
        return []

    missing_square_brackets = cleaned.count("[") - cleaned.count("]")
    if missing_square_brackets > 0:
        insert_pos = cleaned.rfind("}")
        if insert_pos >= 0:
            cleaned = (
                cleaned[:insert_pos]
                + "\n"
                + ("]" * missing_square_brackets)
                + "\n"
                + cleaned[insert_pos:]
            )

    try:
        payload = json.loads(f"[{cleaned}]")
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON-like sample %s: %s", path.name, exc)
        return []

    return [row for row in payload if isinstance(row, dict)]


def _strip_json_like_comment(line: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        if escaped:
            result.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\" and in_string:
            result.append(char)
            escaped = True
            index += 1
            continue
        if char == '"':
            result.append(char)
            in_string = not in_string
            index += 1
            continue
        if not in_string and line[index : index + 2] == "--":
            break
        result.append(char)
        index += 1

    cleaned = "".join(result).rstrip()
    if ",-" in cleaned:
        cleaned = cleaned.split(",-", 1)[0] + ","
    if ",指标" in cleaned:
        cleaned = cleaned.split(",指标", 1)[0] + ","
    return cleaned


def _filter_templates(records: list[dict[str, Any]], body: TemplateListRequest) -> list[dict[str, Any]]:
    result = []
    keyword = body.proj_name.strip().lower()
    for record in records:
        if body.type_cd and str(record.get("typeCd") or "") != body.type_cd:
            continue
        if body.proj_status_cd and str(record.get("projStatusCd") or "") != body.proj_status_cd:
            continue
        if body.origin_type_cd and str(record.get("originTypeCd") or "") != body.origin_type_cd:
            continue
        if body.proj_type_no and str(record.get("projTypeNo") or "") != body.proj_type_no:
            continue
        if body.is_new_version and str(record.get("isNewVersion") or "") != body.is_new_version:
            continue
        if keyword and keyword not in str(record.get("projName") or "").lower():
            continue
        result.append(record)
    return result


def _filter_activities(records: list[dict[str, Any]], body: ActivitySearchRequest) -> list[dict[str, Any]]:
    keyword = _activity_keyword(body)
    result = []
    seen: set[str] = set()
    for record in records:
        act_no = str(record.get("actNo") or record.get("act_no") or "")
        act_name = str(record.get("actName") or record.get("act_name") or "")
        activity_type = str(record.get("activity_type") or record.get("活动类型") or "")
        target_segment = str(record.get("target_segment") or record.get("目标客群") or "")
        if act_no in seen:
            continue
        if keyword and (
            keyword not in act_no.lower()
            and keyword not in act_name.lower()
            and keyword not in activity_type.lower()
            and keyword not in target_segment.lower()
        ):
            continue
        if body.act_status_cd and str(record.get("actStatusCd") or "") != body.act_status_cd:
            continue
        if body.act_type_cd and str(record.get("actTypeCd") or "") != body.act_type_cd:
            continue
        if body.act_src_cd and str(record.get("actSrcCd") or "") != body.act_src_cd:
            continue
        if body.creator_no and str(record.get("creatorNo") or "") != body.creator_no:
            continue
        if body.channel and body.channel.lower() not in str(record.get("channel") or "").lower():
            continue
        if body.act_start_dt and str(record.get("actStartDt") or "") < body.act_start_dt:
            continue
        if body.act_end_dt and str(record.get("actEndDt") or "") > body.act_end_dt:
            continue
        seen.add(act_no)
        result.append(record)
    return result


def _campaigns_to_activity_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for record in records:
        act_no = str(record.get("活动编号") or "")
        act_name = str(record.get("活动名称") or "")
        activity_type = str(record.get("活动类型") or "")
        channel = str(record.get("活动渠道") or "")
        target_segment = str(record.get("目标客群") or "")
        rows.append(
            {
                "actNo": act_no,
                "actName": act_name,
                "actTypeCd": "Y",
                "actSrcCd": "01",
                "actStartDt": _format_date(record.get("活动开始日期")),
                "actEndDt": _format_date(record.get("活动结束日期")),
                "actStatusCd": _status_code(record.get("活动状态")),
                "actDesc": record.get("活动内容"),
                "creatorAfltOrgNo": "001",
                "creatorAfltOrgName": "演示银行",
                "creatorNo": "1000001",
                "creatorName": "Mock",
                "createTm": f"{_format_date(record.get('活动开始日期'))} 09:00:00",
                "updateTm": f"{_format_date(record.get('活动结束日期'))} 18:00:00",
                "sginAct": 0,
                "sginActType": None,
                # Business classification fields for agent search/report.
                "activity_type": activity_type,
                "channel": channel,
                "target_segment": target_segment,
                "到期理财产品数": record.get("到期理财产品数"),
                "到期理财金额": record.get("到期理财金额"),
                "到期客户数": record.get("到期客户数"),
                "到期后转化率": record.get("到期后转化率"),
                "到期后再购金额": record.get("到期后再购金额"),
                "到期后再购客户数": record.get("到期后再购客户数"),
                "上月末AUM时点值": record.get("上月末AUM时点值"),
                "上个月理财余额": record.get("上个月理财余额"),
                # Compatibility fields for internal consumers.
                "activity_id": act_no,
                "act_no": act_no,
                "act_name": act_name,
                "活动编号": act_no,
                "活动名称": act_name,
                "活动状态": record.get("活动状态"),
                "活动运营目标": record.get("活动运营目标"),
                "活动类型": activity_type,
                "活动渠道": channel,
                "目标客群": target_segment,
            }
        )
    return rows


def _paginate(rows: list[dict[str, Any]], page_num: int, page_size: int) -> list[dict[str, Any]]:
    start = (page_num - 1) * page_size
    end = start + page_size
    return rows[start:end]


def _activity_keyword(body: ActivitySearchRequest) -> str:
    return (body.act_no or body.act_name or "").strip().lower()


def _format_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return ""
    text = str(value)
    return text[:10] if len(text) >= 10 else text


def _status_code(value: Any) -> str:
    text = str(value or "")
    if "进行中" in text:
        return "Y6"
    if "结束" in text:
        return "Y8"
    return "Y7" if text else ""


def _select_campaign_records(act_nos: list[str]) -> list[dict[str, Any]]:
    records = load_data()
    if not act_nos:
        return records[:3]
    wanted = {str(act_no) for act_no in act_nos}
    return [record for record in records if str(record.get("活动编号") or "") in wanted]


def _resolve_activity_refs(act_nos: list[str], records: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_id = {str(record.get("活动编号") or ""): record for record in records}
    # 活动搜索样例报文中的活动（PV 开头）不在 Excel 数据源里，名称需从这里取。
    sample_names = {
        str(row.get("actNo") or ""): str(row.get("actName") or "")
        for row in _load_json_rows(_ACTIVITY_SAMPLE_PATH)
    }
    activities = []
    for act_no in act_nos:
        act_no = str(act_no)
        record = by_id.get(act_no)
        activities.append(
            {
                "act_no": act_no,
                "actName": str(
                    (record or {}).get("活动名称")
                    or sample_names.get(act_no)
                    or _SAMPLE_ACTIVITY_NAMES.get(act_no)
                    or f"活动{act_no[-6:]}"
                ),
            }
        )
    return activities


def _metric_sum(records: list[dict[str, Any]], field_name: str, default: float, act_nos: list[str]) -> float:
    total = _sum_number(records, field_name)
    if total:
        return total
    if not act_nos:
        return default
    return sum(_deterministic_number(act_no, default / max(len(act_nos), 1)) for act_no in act_nos)


def _sum_number(records: list[dict[str, Any]], field_name: str) -> float:
    total = 0.0
    for record in records:
        value = record.get(field_name)
        if isinstance(value, (int, float)):
            total += float(value)
        elif isinstance(value, str):
            try:
                total += float(value)
            except ValueError:
                pass
    return total


def _avg_number(records: list[dict[str, Any]], field_name: str) -> float:
    values = []
    for record in records:
        value = record.get(field_name)
        if isinstance(value, (int, float)):
            values.append(float(value))
        elif isinstance(value, str):
            try:
                values.append(float(value))
            except ValueError:
                pass
    return round(sum(values) / len(values), 4) if values else 0.0


def _deterministic_number(seed_text: str, base: float) -> float:
    seed = sum(ord(char) for char in seed_text)
    return round(base * (0.75 + (seed % 50) / 100), 2)


def _period_text(etl_dt_start: str, etl_dt_end: str) -> tuple[str, str]:
    start = etl_dt_start or "2026-06-01"
    end = etl_dt_end or "2026-06-30"
    return (f"{start},{end}", f"{start},{end}")


def _front_calc_indicator(
    ind_sort_no: int,
    ind_seq_no: int,
    show_name: str,
    formula: str,
    cfg_content: str | None = None,
) -> dict[str, Any]:
    indicator = {
        "indSortNo": ind_sort_no,
        "indSeqNo": ind_seq_no,
        "indexName": "前端运算指标",
        "indexNo": "前端运算指标",
        "indexShowName": show_name,
        "isForeEndCalc": "1",
        "plateRuleCfgInfList": [{"cfgContent": formula}],
        "showFlag": "1",
    }
    if cfg_content is not None:
        indicator["cfgContent"] = cfg_content
    return indicator


def _indicator(
    ind_sort_no: int,
    ind_seq_no: int,
    index_name: str,
    index_no: str,
    show_name: str,
    value: float | int,
) -> dict[str, Any]:
    return {
        "indSortNo": ind_sort_no,
        "indSeqNo": ind_seq_no,
        "indexName": index_name,
        "indexNo": index_no,
        "indexShowName": show_name,
        "isForeEndCalc": "0",
        "showFlag": "1",
        "resData": [{index_no: value}],
    }


def _period_indicator(ind_sort_no: int, ind_seq_no: int, cfg_content: str, value: float) -> dict[str, Any]:
    return {
        "indSortNo": ind_sort_no,
        "indSeqNo": ind_seq_no,
        "cfgContent": cfg_content,
        "indexName": "AUM时点值",
        "indexNo": "I100003",
        "indexShowName": "AUM时点值求和",
        "isForeEndCalc": "0",
        "showFlag": "1",
        "resData": [{"I100003": value}],
    }


def _customer_level_rows(total_customers: int) -> list[dict[str, Any]]:
    levels = [
        ("私人银行客户", 0.08),
        ("白金卡客户", 0.17),
        ("银卡N2客户", 0.35),
        ("银卡N1客户", 0.18),
        ("银卡N0客户", 0.22),
    ]
    return [
        {
            "I200040": max(int(total_customers * ratio), 1),
            "new_lvl": level,
            "old_lvl": level,
        }
        for level, ratio in levels
    ]


def _multi_activity_indicators(
    activities: list[dict[str, str]],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(record.get("活动编号") or ""): record for record in records}
    indicators = []
    for index, activity in enumerate(activities):
        act_no = activity["act_no"]
        record = by_id.get(act_no, {})
        customers = int(_sum_number([record], "活动运营人数") or _deterministic_number(act_no, 85000))
        avg_aum = round(_avg_number([record], "人均aum值") or _deterministic_number(act_no, 3.8), 2)
        base = {"act_no": act_no, "actName": activity["actName"]}
        indicators.append(
            {
                "indSortNo": index * 2,
                "indSeqNo": 1,
                "indexName": "前端运算指标",
                "indexNo": "前端运算指标",
                "indexShowName": "AUM均值",
                "isForeEndCalc": "1",
                "plateRuleCfgInfList": [{"cfgContent": "$I1000030$/$I2000011"}],
                "showFlag": "1",
                "resData": [base | {"AUM均值": avg_aum}],
            }
        )
        indicators.append(
            {
                "indSortNo": index * 2 + 1,
                "indSeqNo": 2,
                "indexName": "客户编号",
                "indexNo": "I200001",
                "indexShowName": "源名单客户数",
                "isForeEndCalc": "0",
                "showFlag": "1",
                "resData": [base | {"I200001": customers}],
            }
        )
    return indicators


def _dimension_indicators(project_no: str, total_customers: int) -> list[dict[str, Any]]:
    rules = [
        {
            "cfgTypeCd": "2",
            "cfgTypeName": "AUM时点值",
            "srcTableName": "COAP_DATA.COAP_CUST_BIZ_VAL_ANALY",
        },
        _dimension_rule("所属分行名称", "I200174", [("杭州分行", "200"), ("上海分行", "206"), ("北京分行", "215")]),
        _dimension_rule("性别代码", "I200176", [("男", "02"), ("女", "03")]),
    ]
    rows = [
        {"I200174": "上海分行", "I200176": "男", "totalCount": max(int(total_customers * 0.19), 1)},
        {"I200174": "杭州分行", "I200176": "男", "totalCount": max(int(total_customers * 0.31), 1)},
        {"I200174": "北京分行", "I200176": "女", "totalCount": max(int(total_customers * 0.12), 1)},
    ]
    return [
        {
            "indSortNo": 0,
            "indSeqNo": 1,
            "indexName": "AUM时点值",
            "indexNo": "I200013",
            "indexShowName": "AUM时点值1",
            "isForeEndCalc": "0",
            "plateRuleCfgInfList": rules,
            "plateTypeCd": "5",
            "projNo": project_no,
            "showFlag": "1",
            "resData": rows,
        },
        {
            "indSortNo": 1,
            "indSeqNo": 2,
            "indexName": "前端运算指标",
            "indexNo": "前端运算指标",
            "indexShowName": "前端运算指标",
            "isForeEndCalc": "1",
            "plateRuleCfgInfList": [
                {
                    "cfgContent": "$I1000030$/$I2000011",
                    "cfgTypeCd": "2",
                    "cfgTypeName": "前端运算指标",
                    "srcTableName": None,
                },
                rules[1],
                rules[2],
            ],
            "plateTypeCd": "5",
            "projNo": project_no,
            "showFlag": "1",
            "resData": [
                {**row, "totalCount": round(float(row["totalCount"]) * 1000.25, 2)}
                for row in rows
            ],
        },
    ]


def _dimension_rule(index_name: str, index_no: str, segments: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "indexName": index_name,
        "indexNo": index_no,
        "cfgTypeCd": "1",
        "especChartIndRuleCfgInfs": [
            {
                "indexNo": index_no,
                "segEnd": code,
                "segName": name,
                "segSort": idx + 1,
                "segStart": code,
            }
            for idx, (name, code) in enumerate(segments)
        ],
        "orderNum": "1" if index_no == "I200174" else "2",
    }
