"""component_value_fetch 的取数日期口径测试：T-2 规则作用于接口入参。"""
from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

from src.report_pipeline.capabilities import component_value_fetch as cvf
from src.report_pipeline.period import compute_analysis_period as _real_period


def _patch_llm_and_prompt(monkeypatch):
    monkeypatch.setattr(cvf, "format_runtime_prompt", lambda *a, **k: "")

    async def fake_invoke(prompt, **kwargs):
        return SimpleNamespace(content="{}")

    fake_model = SimpleNamespace(invoke=fake_invoke)
    monkeypatch.setattr(cvf, "get_model", lambda *a, **k: fake_model)


def _state(activities):
    return {
        "template_match_result": {
            "template_id": "tpl-1",
            "activity_ids": [a["activity_id"] for a in activities],
            "dependent_components": [],
        },
        "matched_data_templates": [],
        "marketing_intent": {},
        "activity_list": activities,
    }


def test_component_params_use_t_minus_2_when_activity_ongoing(monkeypatch):
    _patch_llm_and_prompt(monkeypatch)
    captured = []

    def fake_fetch(params):
        captured.append(params)
        return SimpleNamespace(success=True, data={"x": 1}, error="")

    monkeypatch.setattr(cvf, "fetch_component_values", fake_fetch)
    # 固定 today=2026-07-21，使 T-2=2026-07-19 可断言
    monkeypatch.setattr(
        cvf, "compute_analysis_period",
        lambda activities, today: _real_period(activities, date(2026, 7, 21)),
    )
    activities = [
        {"activity_id": "a1", "start_date": "2026-04-01", "end_date": "2026-05-01"},
        {"activity_id": "a2", "start_date": "2026-07-01", "end_date": "2026-08-30"},
    ]
    asyncio.run(cvf.component_value_fetch_node(_state(activities)))

    assert captured, "fetch_component_values 未被调用"
    assert captured[0]["start_date"] == "2026-04-01"
    assert captured[0]["end_date"] == "2026-07-19"


def test_component_params_use_max_end_when_all_ended(monkeypatch):
    _patch_llm_and_prompt(monkeypatch)
    captured = []
    monkeypatch.setattr(
        cvf, "fetch_component_values",
        lambda params: captured.append(params) or SimpleNamespace(success=True, data={"x": 1}, error=""),
    )
    activities = [
        {"activity_id": "a1", "start_date": "2026-04-01", "end_date": "2026-05-01"},
        {"activity_id": "a2", "start_date": "2026-03-01", "end_date": "2026-06-30"},
    ]
    asyncio.run(cvf.component_value_fetch_node(_state(activities)))

    assert captured[0]["start_date"] == "2026-03-01"
    assert captured[0]["end_date"] == "2026-06-30"
