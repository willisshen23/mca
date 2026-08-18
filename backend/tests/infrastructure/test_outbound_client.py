"""外呼活动查询 client 多活动支持测试（mock _request_api，无网络）。"""
from __future__ import annotations

from src.infrastructure.integrations.bank_marketing.client import BankMarketingApiClient
from src.infrastructure.integrations.bank_marketing.schemas import ApiResult

TRADE = "EDW_RTL_MED_ACTIVITY_BASE_INFO"


def _client_with_fake_api(monkeypatch, rows_by_trade=None):
    client = BankMarketingApiClient()
    captured = []

    def fake_request(api_name, url, method, params):
        captured.append({"url": url, "params": params})
        trade_code = url.rsplit("/", 1)[-1]
        rows = (rows_by_trade or {}).get(trade_code, [])
        return ApiResult(
            success=True,
            data={"retCode": "000000", "totalCount": len(rows), "result": rows},
        )

    monkeypatch.setattr(client, "_request_api", fake_request)
    return client, captured


def test_extract_act_nos_from_string():
    client = BankMarketingApiClient()
    assert client._extract_outbound_act_nos({"act_no": " A "}) == ["A"]


def test_extract_act_nos_from_list_dedup_preserves_order():
    client = BankMarketingApiClient()
    assert client._extract_outbound_act_nos({"act_no": ["A", " B ", "A", ""]}) == ["A", "B"]


def test_extract_act_no_legacy_returns_first():
    client = BankMarketingApiClient()
    assert client._extract_outbound_act_no({"act_no": ["A", "B"]}) == "A"
    assert client._extract_outbound_act_no({"act_no": "A"}) == "A"


def test_edw_act_no_joined_for_multiple_activities(monkeypatch):
    client, captured = _client_with_fake_api(monkeypatch)
    client.get_outbound_activity_data({"act_no": ["A", "B", "C"]})
    assert captured, "未发起任何 trade_code 请求"
    for call in captured:
        assert call["params"]["pms"]["edw_act_no"] == "A','B','C"


def test_edw_act_no_single_activity_stays_bare(monkeypatch):
    client, captured = _client_with_fake_api(monkeypatch)
    client.get_outbound_activity_data({"act_no": "A"})
    assert captured[0]["params"]["pms"]["edw_act_no"] == "A"


def test_matched_act_nos_aggregated_from_rows(monkeypatch):
    rows = [{"act_no": "B", "act_name": "乙"}, {"act_no": "A", "act_name": "甲"}]
    client, _ = _client_with_fake_api(monkeypatch, rows_by_trade={TRADE: rows})
    result = client.get_outbound_activity_data({"act_no": ["A", "B", "C"]})
    assert result.success
    assert result.data["matched"] is True
    assert result.data["matched_act_nos"] == ["B", "A"]
    assert result.data["act_no"] == ["A", "B", "C"]
    assert result.data["activity_id"] == ["A", "B", "C"]


def test_single_activity_data_keeps_string_act_no(monkeypatch):
    rows = [{"act_no": "A", "act_name": "甲"}]
    client, _ = _client_with_fake_api(monkeypatch, rows_by_trade={TRADE: rows})
    result = client.get_outbound_activity_data({"act_no": "A"})
    assert result.data["act_no"] == "A"
    assert result.data["matched_act_nos"] == ["A"]


def test_empty_act_no_returns_error():
    client = BankMarketingApiClient()
    result = client.get_outbound_activity_data({"act_no": ["", "  "]})
    assert not result.success
    assert "缺少act_no" in result.error
