"""compute_analysis_period 日期口径测试（设计文档 §5.2）。"""
from __future__ import annotations

from datetime import date

from src.report_pipeline.period import compute_analysis_period

TODAY = date(2026, 7, 21)
T_MINUS_2 = "2026-07-19"


def test_all_ended_takes_max_end():
    activities = [
        {"start_date": "2026-04-01", "end_date": "2026-05-01"},
        {"start_date": "2026-03-01", "end_date": "2026-06-30"},
    ]
    assert compute_analysis_period(activities, TODAY) == {
        "start_date": "2026-03-01",
        "end_date": "2026-06-30",
    }


def test_ongoing_activity_by_future_end_uses_t_minus_2():
    activities = [
        {"start_date": "2026-04-01", "end_date": "2026-05-01"},
        {"start_date": "2026-07-01", "end_date": "2026-08-30"},  # 未结束
    ]
    assert compute_analysis_period(activities, TODAY) == {
        "start_date": "2026-04-01",
        "end_date": T_MINUS_2,
    }


def test_end_today_counts_as_ongoing():
    activities = [{"start_date": "2026-07-01", "end_date": "2026-07-21"}]
    assert compute_analysis_period(activities, TODAY)["end_date"] == T_MINUS_2


def test_empty_end_date_counts_as_ongoing():
    activities = [{"start_date": "2026-07-01", "end_date": ""}]
    assert compute_analysis_period(activities, TODAY)["end_date"] == T_MINUS_2


def test_t_minus_2_clamped_to_start_when_activity_just_started():
    activities = [{"start_date": "2026-07-20", "end_date": "2026-08-01"}]
    # T-2 = 2026-07-19 早于 start → 钳制为 start，避免起止倒挂
    assert compute_analysis_period(activities, TODAY) == {
        "start_date": "2026-07-20",
        "end_date": "2026-07-20",
    }


def test_bank_field_names_and_date_formats():
    activities = [
        {"actStartDt": "2026/03/05", "actEndDt": "20260601"},
        {"活动开始日期": "2026-02-01", "活动结束日期": "2026-04-01"},
    ]
    assert compute_analysis_period(activities, TODAY) == {
        "start_date": "2026-02-01",
        "end_date": "2026-06-01",
    }


def test_missing_dates_return_empty_strings():
    assert compute_analysis_period([{"name": "无日期"}], date(2026, 1, 1)) == {
        "start_date": "",
        "end_date": "2025-12-30",  # 结束日期缺失按未结束处理 → T-2
    }
