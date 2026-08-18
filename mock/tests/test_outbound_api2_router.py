"""外呼 api2 mock 多活动解析与合并返回测试。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import outbound_api2_router as router  # noqa: E402
import waihu_data_service as data_service  # noqa: E402


def _record(act_no: str, act_name: str) -> dict:
    return {
        "act_no": act_no,
        "basic_info": {
            "act_no": act_no,
            "act_name": act_name,
            "活动状态": "执行中",
            "活动开始时间": "2026-01-01",
        },
        "execution": {"act_no": act_no, "act_name": act_name, "外呼人数": 100},
    }


def test_split_act_nos_single():
    assert router._split_act_nos("A") == ["A"]


def test_split_act_nos_multi_without_outer_quotes():
    assert router._split_act_nos("A','B','C") == ["A", "B", "C"]


def test_split_act_nos_multi_with_outer_quotes():
    assert router._split_act_nos("'A','B','C'") == ["A", "B", "C"]


def test_split_act_nos_list_passthrough_dedup():
    assert router._split_act_nos(["A", "B", "A", " "]) == ["A", "B"]


def test_extract_act_nos_from_pms():
    body = {"pms": {"edw_act_no": "A','B"}}
    assert router._extract_act_nos(body) == ["A", "B"]


def test_get_activities_by_ids(monkeypatch):
    monkeypatch.setattr(
        data_service, "load_data", lambda: [_record("A", "甲"), _record("B", "乙")]
    )
    assert set(data_service.get_activities_by_ids(["A", "B", "C"])) == {"A", "B"}
    assert data_service.get_activities_by_ids([]) == {}


def test_query_multi_activity_merges_rows(monkeypatch):
    records = {"A": _record("A", "甲"), "B": _record("B", "乙")}
    monkeypatch.setattr(
        router,
        "get_activities_by_ids",
        lambda act_nos: {a: records[a] for a in act_nos if a in records},
    )
    body = {"pms": {"edw_act_no": "A','B"}, "props": {"limit": 20, "start": 1}}
    resp = router._query_outbound_data("EDW_RTL_MED_ACTIVITY_BASE_INFO", body)
    assert resp["retCode"] == "000000"
    assert [row["act_no"] for row in resp["result"]] == ["A", "B"]


def test_query_multi_activity_skips_missing(monkeypatch):
    records = {"A": _record("A", "甲")}
    monkeypatch.setattr(
        router,
        "get_activities_by_ids",
        lambda act_nos: {a: records[a] for a in act_nos if a in records},
    )
    body = {"pms": {"edw_act_no": "A','MISSING"}}
    resp = router._query_outbound_data("EDW_RTL_MED_ACTIVITY_BASE_INFO", body)
    assert [row["act_no"] for row in resp["result"]] == ["A"]


def test_query_single_activity_still_works(monkeypatch):
    records = {"A": _record("A", "甲")}
    monkeypatch.setattr(
        router,
        "get_activities_by_ids",
        lambda act_nos: {a: records[a] for a in act_nos if a in records},
    )
    body = {"pms": {"edw_act_no": "A"}}
    resp = router._query_outbound_data("EDW_RTL_MED_ACTIVITY_BASE_INFO", body)
    assert [row["act_no"] for row in resp["result"]] == ["A"]


def test_real_excel_supports_multi_activity():
    records = data_service.get_activities_by_ids(
        ["ACT20260116906568", "ACT20260116906569", "ACT20260116906570", "NOT_EXIST"]
    )
    assert set(records) == {"ACT20260116906568", "ACT20260116906569", "ACT20260116906570"}
    body = {"pms": {"edw_act_no": "ACT20260116906568','ACT20260116906569"}}
    resp = router._query_outbound_data("EDW_RTL_MED_ACTIVITY_BASE_INFO", body)
    assert {row["act_no"] for row in resp["result"]} == {
        "ACT20260116906568",
        "ACT20260116906569",
    }
