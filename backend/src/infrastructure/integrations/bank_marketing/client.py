from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from src.config import get_settings
from src.infrastructure.integrations.bank_marketing.schemas import ApiResult
from src.domain.report.template_skill import merge_template_skill_order

logger = logging.getLogger("njbank.agent")


class BankMarketingApiClient:
    """HTTP adapter for bank marketing APIs.

    API addresses are configured through environment variables instead of being
    hard-coded in agent nodes. The adapter normalizes upstream responses into
    ApiResult so the agent workflow can stay decoupled from transport
    details and vendor response envelopes.
    """

    def get_activity_list(self, params: dict) -> ApiResult:
        params = self._normalize_activity_params(params)
        logger.info("活动API：活动查询请求参数 %s", params)
        result = self._request_api(
            api_name="活动API",
            url=self._settings.bank_marketing_activity_list_url,
            method=self._settings.bank_marketing_activity_list_method,
            params=params,
        )
        if result.success:
            result.data = [self._normalize_activity(item) for item in result.data or []]
        return result

    def get_template_list(self, params: dict) -> ApiResult:
        result = self._request_api(
            api_name="数据模板列表API",
            url=self._settings.bank_marketing_template_list_url,
            method=self._settings.bank_marketing_template_list_method,
            params=self._build_template_list_query(params),
        )
        if result.success:
            result.data = [self._normalize_template(item) for item in result.data or []]
        return result

    def get_component_values(self, params: dict) -> ApiResult:
        return self._request_api(
            api_name="组件数值API",
            url=self._settings.bank_marketing_component_values_url,
            method=self._settings.bank_marketing_component_values_method,
            params=self._build_component_values_query(params),
        )

    def get_outbound_activity_data(self, params: dict) -> ApiResult:
        if "{trade_code}" in self._settings.bank_marketing_outbound_activity_data_url:
            return self._get_outbound_activity_data_from_trade_apis(params)
        return self._get_legacy_outbound_activity_data(params)

    def _get_legacy_outbound_activity_data(self, params: dict) -> ApiResult:
        url = self._build_outbound_activity_data_url(params)
        request_params = (
            {}
            if "{act_no}" in self._settings.bank_marketing_outbound_activity_data_url
            else self._build_legacy_outbound_activity_data_params(params)
        )
        return self._request_api(
            api_name="外呼活动查询API",
            url=url,
            method=self._settings.bank_marketing_outbound_activity_data_method,
            params=request_params,
        )

    def _get_outbound_activity_data_from_trade_apis(self, params: dict) -> ApiResult:
        act_nos = self._extract_outbound_act_nos(params)
        if not act_nos:
            return ApiResult(success=False, error="外呼活动查询缺少act_no/activity_id")

        edw_act_no = "','".join(act_nos)
        sources: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        any_success = False
        matched = False
        matched_act_nos: list[str] = []
        trade_codes = self._outbound_activity_trade_codes()
        if not trade_codes:
            return ApiResult(success=False, error="外呼活动交易码未配置")

        for trade_code in trade_codes:
            url = self._build_outbound_trade_api_url(trade_code)
            request_params = self._build_outbound_trade_api_params(params, edw_act_no)
            result = self._request_api(
                api_name=f"外呼活动查询API[{trade_code}]",
                url=url,
                method=self._settings.bank_marketing_outbound_activity_data_method,
                params=request_params,
            )
            if not result.success:
                errors[trade_code] = result.error
                sources[trade_code] = {"totalCount": 0, "result": [], "error": result.error}
                continue

            any_success = True
            rows = self._normalize_outbound_trade_rows(result.data)
            total_count = len(rows)
            if total_count > 0:
                matched = True
            for row in rows:
                row_act_no = str(row.get("act_no") or "").strip()
                if row_act_no and row_act_no not in matched_act_nos:
                    matched_act_nos.append(row_act_no)
            sources[trade_code] = {
                "totalCount": total_count,
                "result": rows,
            }

        if not any_success:
            return ApiResult(success=False, error="; ".join(errors.values()) or "外呼活动查询API全部失败")

        total_count = sum(source.get("totalCount", 0) for source in sources.values())
        act_no_value: str | list[str] = act_nos[0] if len(act_nos) == 1 else act_nos
        data = {
            "matched": matched,
            "activity_id": act_no_value,
            "act_no": act_no_value,
            "matched_act_nos": matched_act_nos,
            "source": "outbound_activity_trade_apis",
            "totalCount": total_count,
            "sources": sources,
        }
        if errors:
            data["errors"] = errors
        return ApiResult(
            success=True,
            data=data,
            meta={
                "count": total_count,
                "matched": matched,
                "trade_codes": trade_codes,
            },
        )

    def _outbound_activity_trade_codes(self) -> list[str]:
        configured = self._settings.bank_marketing_outbound_activity_trade_codes
        return [code.strip() for code in configured.split(",") if code.strip()]

    @property
    def _settings(self):
        return get_settings()

    def _request_api(
        self,
        api_name: str,
        url: str,
        method: str,
        params: dict | None = None,
    ) -> ApiResult:
        params = params or {}
        url = (url or "").strip()
        if not url:
            return ApiResult(
                success=False,
                error=f"{api_name}地址未配置，请设置该接口的完整 URL",
            )

        method = method.upper().strip() or "POST"
        request_body = None
        if method == "GET" and params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(params, doseq=True)}"
        else:
            request_body = json.dumps(params, ensure_ascii=False).encode("utf-8")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        token = self._settings.bank_marketing_api_token.strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        request = Request(url=url, data=request_body, headers=headers, method=method)
        timeout = self._settings.bank_marketing_api_timeout_seconds

        logger.info("%s请求开始: method=%s url=%s params=%s", api_name, method, url, params)
        try:
            with urlopen(request, timeout=timeout) as response:
                response_text = response.read().decode("utf-8")
                status_code = getattr(response, "status", 200)
            logger.info("%s原始返回: status=%s body=%s", api_name, status_code, response_text)
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            logger.error("%s HTTP失败: status=%s body=%s", api_name, exc.code, error_body[:500])
            return ApiResult(success=False, error=f"HTTP {exc.code}: {error_body or exc.reason}")
        except URLError as exc:
            logger.error("%s连接失败: %s", api_name, str(exc.reason))
            return ApiResult(success=False, error=f"连接失败: {str(exc.reason)}")
        except TimeoutError:
            logger.error("%s请求超时: timeout=%ss", api_name, timeout)
            return ApiResult(success=False, error=f"请求超时（{timeout}s）")
        except Exception as exc:
            logger.exception("%s调用异常", api_name)
            return ApiResult(success=False, error=str(exc))

        try:
            payload = json.loads(response_text) if response_text else {}
        except json.JSONDecodeError as exc:
            logger.error("%s响应不是合法JSON: %s", api_name, response_text[:500])
            return ApiResult(success=False, error=f"响应JSON解析失败: {str(exc)}")

        result = self._normalize_payload(payload, status_code)
        logger.info(
            "%s请求完成: success=%s status=%s count=%s",
            api_name,
            result.success,
            status_code,
            result.meta.get("count", "-"),
        )
        return result

    def _build_outbound_activity_data_url(self, params: dict) -> str:
        url = self._settings.bank_marketing_outbound_activity_data_url
        act_no = self._extract_outbound_act_no(params)
        if "{act_no}" in url:
            if not act_no:
                logger.warning("外呼活动查询缺少act_no/activity_id: params=%s", params)
            return url.replace("{act_no}", quote(act_no, safe=""))
        return url

    def _build_outbound_trade_api_url(self, trade_code: str) -> str:
        return self._settings.bank_marketing_outbound_activity_data_url.replace(
            "{trade_code}",
            quote(trade_code, safe=""),
        )

    def _build_outbound_trade_api_params(self, params: dict, edw_act_no: str) -> dict:
        raw_props = params.get("props") if isinstance(params.get("props"), dict) else {}
        raw_pms = params.get("pms") if isinstance(params.get("pms"), dict) else {}
        pms = {
            "edw_act_no": edw_act_no,
            "edw_customer_segment": raw_pms.get("edw_customer_segment") or "",
            "edw_product_type": raw_pms.get("edw_product_type") or "",
        }
        return {
            "pms": pms,
            "props": {
                "limit": raw_props.get("limit") or params.get("limit") or 200,
                "start": raw_props.get("start") or params.get("start") or 1,
                "identity": self._build_identity(params),
                "seqNo": self._build_seq_no(params),
            },
        }

    def _build_legacy_outbound_activity_data_params(self, params: dict) -> dict:
        act_no = self._extract_outbound_act_no(params)
        request_params = {
            key: value
            for key, value in (params or {}).items()
            if key
            not in {
                "activity",
                "start_date",
                "startDate",
                "end_date",
                "endDate",
                "actStartDt",
                "actEndDt",
                "edw_start_dt",
                "edw_end_dt",
            }
        }
        if act_no:
            request_params["act_no"] = act_no
            request_params["activity_id"] = act_no
        return request_params

    def _build_identity(self, params: dict) -> str:
        """Build Base64-encoded identity for outbound activity trade APIs.

        Format: userId||orgNo||channel||timestampMs
        Empty parts fall back to configured defaults so the result always
        contains 3 separators and 4 components.
        """
        user_id = params.get("user_id") or self._settings.bank_marketing_default_user_id
        org_no = params.get("org_no") or self._settings.bank_marketing_default_org_no
        channel = params.get("channel") or self._settings.bank_marketing_default_channel
        timestamp_ms = str(int(time.time() * 1000))
        raw = f"{user_id}||{org_no}||{channel}||{timestamp_ms}"
        return base64.b64encode(raw.encode("utf-8")).decode("ascii")

    def _build_seq_no(self, params: dict) -> str:
        """Return seqNo from params or generate a fresh request serial number."""
        return params.get("seqNo") or uuid.uuid4().hex

    def _extract_outbound_act_nos(self, params: dict) -> list[str]:
        """提取活动编号列表：act_no/activity_id 兼容 str 或 list，去重保序去空白。"""
        activity = params.get("activity") if isinstance(params.get("activity"), dict) else {}
        value = (
            params.get("act_no")
            or params.get("activity_id")
            or activity.get("act_no")
            or activity.get("activity_id")
            or activity.get("actNo")
            or activity.get("活动编号")
            or ""
        )
        items = value if isinstance(value, (list, tuple)) else [value]
        act_nos: list[str] = []
        for item in items:
            text = str(item).strip()
            if text and text not in act_nos:
                act_nos.append(text)
        return act_nos

    def _extract_outbound_act_no(self, params: dict) -> str:
        act_nos = self._extract_outbound_act_nos(params)
        return act_nos[0] if act_nos else ""

    def _normalize_outbound_trade_rows(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            if isinstance(data.get("result"), list):
                return [row for row in data["result"] if isinstance(row, dict)]
            if isinstance(data.get("data"), list):
                return [row for row in data["data"] if isinstance(row, dict)]
            if data.get("matched") is False:
                return []
            return [data] if data else []
        return []

    def _normalize_payload(self, payload: Any, status_code: int) -> ApiResult:
        if isinstance(payload, list):
            return ApiResult(success=True, data=payload, meta={"status_code": status_code, "count": len(payload)})

        if not isinstance(payload, dict):
            return ApiResult(success=False, error="接口响应格式不支持", meta={"status_code": status_code})

        success = self._is_success_payload(payload)
        if success is False:
            return ApiResult(
                success=False,
                error=str(payload.get("error") or payload.get("message") or payload.get("detail") or "接口返回失败"),
                meta={"status_code": status_code},
            )

        data = self._extract_data(payload)
        count = len(data) if isinstance(data, (list, dict)) else None
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        meta = {**meta, "status_code": status_code}
        if count is not None:
            meta["count"] = count
        return ApiResult(success=True, data=data, meta=meta)

    def _extract_data(self, payload: dict) -> Any:
        for key in ("data", "result", "rows", "campaigns", "templates", "component_values", "values"):
            if key in payload:
                return payload[key]
        return payload

    def _is_success_payload(self, payload: dict) -> bool | None:
        success = payload.get("success")
        if isinstance(success, bool):
            return success
        if isinstance(success, str):
            normalized = success.strip().lower()
            if normalized in {"true", "success", "ok", "1"}:
                return True
            if normalized in {"false", "fail", "failed", "error", "0"}:
                return False

        code = payload.get("code", payload.get("status", payload.get("retCode")))
        if code is None:
            return None
        return str(code).strip() in {"0", "000000", "200", "success", "ok"}

    def _normalize_activity_params(self, params: dict) -> dict:
        normalized = dict(params)
        return self._build_activity_keyword_query(normalized)

    def _build_activity_keyword_query(self, params: dict) -> dict:
        """Build the keyword-search request body for 通过活动关键词查询活动信息api.

        All activity search text is sent through ``actName``. The upstream
        request intentionally omits ``actNo``.
        """
        act_name = str(
            params.get("actName")
            or params.get("keyword")
            or params.get("q")
            or params.get("actNo")
            or ""
        ).strip()
        label_no_list = params.get("labelNoList")
        if not isinstance(label_no_list, list):
            label_no_list = []
        return {
            "srcSysNo": (
                params.get("srcSysNo")
                or params.get("src_sys_no")
                or self._settings.bank_marketing_activity_src_sys_no
                or ""
            ),
            "userNo": (
                params.get("userNo")
                or params.get("user_no")
                or params.get("user_id")
                or self._settings.bank_marketing_default_user_id
                or ""
            ),
            "pageSize": params.get("pageSize") or params.get("limit") or 999,
            "pageNum": params.get("pageNum") or 1,
            "date": params.get("date"),
            "actStatusCd": params.get("actStatusCd", params.get("status", "")) or "",
            "sginAct": params.get("sginAct", "") or "",
            "actSrcCd": params.get("actSrcCd", "") or "",
            "actTypeCd": params.get("actTypeCd", params.get("actTypeCd", "")) or "",
            "labelNoList": label_no_list,
            "actName": act_name,
            "actStartDt": params.get("actStartDt", params.get("start_date", "")) or "",
            "actEndDt": params.get("actEndDt", params.get("end_date", "")) or "",
            "showMallAct": params.get("showMallAct", 1),
            "creatorNo": params.get("creatorNo", "") or "",
            "channel": params.get("channel", "") or "",
        }

    def _build_template_list_query(self, params: dict) -> dict:
        """Build the request body for 获取分析模板列表api.

        The analysis template list is fetched in full for downstream matching,
        so pagination defaults to a large page while leaving the vendor filter
        fields empty unless explicitly supplied. Internal aliases (keyword,
        limit, page) map onto the vendor field names, and any pre-supplied
        vendor fields take precedence.
        """
        params = params or {}
        proj_name = str(
            params.get("projName")
            or params.get("keyword")
            or params.get("q")
            or ""
        ).strip()
        return {
            "pageNum": params.get("pageNum") or params.get("page") or 1,
            "pageSize": params.get("pageSize") or params.get("limit") or 999,
            "typeCd": params.get("typeCd", "1") or "1",
            "projName": params.get("projName", proj_name) or "",
            "projStatusCd": params.get("projStatusCd", "") or "",
            "originTypeCd": params.get("originTypeCd", "") or "",
            "orderType": params.get("orderType", "2") or "2",
            "projTypeNo": params.get("projTypeNo", "") or "",
            "projTypePidNo": params.get("projTypePidNo", "") or "",
            "isNewVersion": params.get("isNewVersion", "1") or "1",
        }

    def _build_component_values_query(self, params: dict) -> dict:
        """Build the request body for 通过分析模板id、活动id、时间范围获取分析模板详情及活动数据api.

        Internal aliases (template_id, activity_ids, start_date, end_date) are
        mapped onto the vendor field names (projNo, actNos, etlDtStart,
        etlDtEnd), while any pre-supplied vendor fields take precedence.
        """
        params = params or {}
        proj_no = str(params.get("projNo") or params.get("template_id") or "").strip()
        act_nos = params.get("actNos")
        if not isinstance(act_nos, list) or not act_nos:
            raw_act_nos = params.get("activity_ids")
            act_nos = raw_act_nos if isinstance(raw_act_nos, list) else []
        act_nos = [str(act_no).strip() for act_no in act_nos if str(act_no).strip()]
        return {
            "projNo": proj_no,
            "etlDtStart": params.get("etlDtStart") or params.get("start_date") or "",
            "etlDtEnd": params.get("etlDtEnd") or params.get("end_date") or "",
            "actNos": act_nos,
        }

    def _normalize_activity(self, item: dict) -> dict:
        if not isinstance(item, dict):
            return {}
        act_no = item.get("activity_id") or item.get("act_no") or item.get("actNo") or item.get("活动编号") or ""
        act_name = (
            item.get("name")
            or item.get("activity_name")
            or item.get("act_name")
            or item.get("actName")
            or item.get("活动名称")
            or ""
        )
        return {
            **item,
            "act_no": act_no,
            "activity_id": act_no,
            "name": act_name,
            "activity_name": item.get("activity_name") or item.get("actName") or act_name,
            "act_name": item.get("act_name") or item.get("actName") or act_name,
            "activity_type": item.get("activity_type") or item.get("actTypeCd") or item.get("活动类型") or "",
            "channel": item.get("channel") or item.get("渠道") or "",
            "start_date": item.get("start_date") or item.get("actStartDt") or item.get("活动开始日期") or "",
            "end_date": item.get("end_date") or item.get("actEndDt") or item.get("活动结束日期") or "",
            "target_segment": item.get("target_segment") or item.get("目标客群") or "",
            "goal": item.get("goal") or item.get("活动运营目标") or "",
            "status": item.get("status") or item.get("actStatusCd") or item.get("活动状态") or "",
        }

    def _normalize_template(self, item: dict) -> dict:
        if not isinstance(item, dict):
            return {}
        normalized = {
            **item,
            "template_id": item.get("template_id") or item.get("projNo") or "",
            "template_name": item.get("template_name") or item.get("name") or item.get("projName") or "",
            "name": item.get("name") or item.get("template_name") or item.get("projName") or "",
            "template_desc": item.get("template_desc") or item.get("description") or item.get("projDesc") or "",
            "scene": item.get("scene") or "activity_analysis",
            "activity_types": item.get("activity_types") or ["online", "offline"],
            "skills": item.get("skills") or item.get("skill_sequence") or item.get("skillSequence") or [],
            "dependent_components": item.get("dependent_components") or self._default_dependent_components(),
        }
        return merge_template_skill_order(normalized)

    def _default_dependent_components(self) -> list[dict]:
        return [
            {"component_id": "overview", "name": "活动概览", "metrics": ["participant_count", "conversion_rate"]},
            {"component_id": "customer_value", "name": "客户价值", "metrics": ["current_aum", "valuable_customers"]},
            {"component_id": "asset_growth", "name": "资产提升", "metrics": ["financial_asset_increase", "deposit_increase"]},
        ]
