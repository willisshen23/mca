"""Agent2 报告合成：用户指定主题色/标题须覆盖默认样式规格的回归测试。

背景：提示词 HTML 技术规范写死"深蓝/白主色调"，用户经 report_theme/
插话提出的主题色只在 user_text 里，两个指令冲突时 LLM 每次只满足一个
（实测红与改标题从未同时落地）。修复后在组装提示词时替换默认规格。
"""

from src.report_pipeline.capabilities.marketing_report_synthesis import (
    _apply_user_style_requirement,
    _extract_style_requirement,
    _resolve_theme_spec,
)


def _state(user_text: str) -> dict:
    return {"original_user_text": user_text}


def test_extract_theme_from_business_params():
    req = _extract_style_requirement(
        "随便生成",
        {"business_params": {"theme_color": "red", "report_title": "银行A活动分析报告"}},
        {},
    )
    assert req["theme"] == "red"
    assert req["title"] == "银行A活动分析报告"


def test_extract_theme_from_instruction_text_fallback():
    # generate_report 工具参数确定性写入"报告主题色：X"，business_params 缺失时兜底
    req = _extract_style_requirement(
        "生成报告；报告主题色：红色；目标活动：X",
        {},
        {},
    )
    assert req["theme"] == "红色"


def test_no_requirement_keeps_default():
    req = _extract_style_requirement("生成活动分析报告", {}, {})
    assert req == {"theme": "", "title": ""}
    prompt = "样式要求\n- 现代响应式设计，深蓝/白主色调，图表卡片具有边框阴影"
    out = _apply_user_style_requirement(prompt, _state("生成活动分析报告"), {}, {})
    assert out == prompt


def test_apply_replaces_hardcoded_blue_spec():
    prompt = "样式要求\n- 现代响应式设计，深蓝/白主色调，图表卡片具有边框阴影"
    out = _apply_user_style_requirement(
        prompt, _state("生成报告"),
        {"business_params": {"theme_color": "red", "report_title": "银行A活动分析报告"}}, {},
    )
    assert "深蓝/白主色调" not in out
    assert "#C62828" in out, "红色规格应带主色号"
    assert "银行A活动分析报告" in out


def test_apply_appends_override_when_default_spec_absent():
    # 运行时提示词覆盖改样、不含默认规格文本时，追加显式覆盖块兜底
    prompt = "样式要求\n- 现代响应式设计"
    out = _apply_user_style_requirement(
        prompt, _state("生成报告；报告主题色：红色"),
        {}, {},
    )
    assert "用户指定样式" in out
    assert "红色" in out


def test_resolve_theme_spec_known_and_unknown():
    assert "#C62828" in _resolve_theme_spec("红色")
    assert "#1565C0" in _resolve_theme_spec("blue")
    assert "「香槟金」" in _resolve_theme_spec("香槟金")


def test_theme_in_seed_instruction_not_original_text():
    """插话场景：original_user_text 是裸插话内容，"报告主题色：X"只在
    seed.messages 的指令文本里（generate_report 工具参数确定性写入）——
    两处合并后必须能提到主题。"""
    from src.report_pipeline.capabilities.marketing_report_synthesis import _combined_user_text

    state = {
        "original_user_text": "报告的色调要是红色",
        "messages": [{"role": "user", "content": "生成报告；报告主题色：red；目标活动：X"}],
    }
    combined = _combined_user_text(state)
    req = _extract_style_requirement(combined, {}, {})
    assert req["theme"] == "red"

    prompt = "样式要求\n- 现代响应式设计，深蓝/白主色调"
    out = _apply_user_style_requirement(prompt, state, {}, {})
    assert "深蓝/白主色调" not in out
    assert "#C62828" in out
