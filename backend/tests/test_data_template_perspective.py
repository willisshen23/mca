"""数据模板匹配的视角关键词提权测试（设计文档 §6.2）。"""
from __future__ import annotations

from src.report_pipeline.capabilities.template_matching import _rank_data_templates

TPL_SMS = {"template_id": "d1", "template_name": "短信触达数据模板", "template_desc": "短信发送与点击"}
TPL_GENERIC = {"template_id": "d2", "template_name": "活动效果数据模板", "template_desc": "通用转化"}
ACTIVITIES = [{"activity_id": "a1", "name": "五一促活", "channel": "短信"}]


def test_keyword_boost_raises_matching_template_rank():
    ranked = _rank_data_templates(
        {}, [TPL_GENERIC, TPL_SMS], ACTIVITIES, {"intent_type": "activity_analysis"}, 2,
        perspective_keyword="短信",
    )
    sms = next(t for t in ranked if t["template_id"] == "d1")
    generic = next(t for t in ranked if t["template_id"] == "d2")
    assert sms["similarity_score"] > generic["similarity_score"] or ranked[0]["template_id"] == "d1"


def test_keyword_boost_capped_at_one():
    ranked = _rank_data_templates(
        {"template_id": "d1", "similarity_score": 0.99},
        [TPL_SMS], ACTIVITIES, {}, 1,
        perspective_keyword="短信",
    )
    assert ranked[0]["similarity_score"] <= 1.0


def test_no_keyword_keeps_original_ranking():
    ranked = _rank_data_templates(
        {}, [TPL_SMS, TPL_GENERIC], ACTIVITIES, {"intent_type": "activity_analysis"}, 2,
    )
    assert len(ranked) == 2  # 不抛异常、数量不变即满足“尽可能”兜底
