"""v3 工具壳的 schema 字段集与 v2 冻结快照等价（防誊写漂移）。

v2 已删除；期望字段集冻结为 v2 退役前的 args_schema 快照（不含 runtime），
改动任一工具参数须同步本快照并确认是有意变更。
"""

from src.agent_v3 import tools as v3_tools

# 12 个业务工具全清单：v2 退役前 args_schema 字段集快照（已剔除 runtime）
_EXPECTED_SCHEMA_FIELDS = {
    'search_activities': ['activity_type', 'channel', 'end_date', 'keyword', 'limit', 'start_date'],
    'get_activity_detail': ['activity_id'],
    'get_available_templates': ['keyword', 'template_type'],
    'get_available_skills': ['category', 'keyword'],
    'parse_uploaded_data': ['confirm'],
    'add_to_analysis_queue': ['activity_ids', 'dimensions', 'metrics', 'perspective'],
    'remove_from_analysis_queue': ['activity_ids'],
    'update_analysis_config': ['activity_id', 'dimensions', 'metrics', 'perspective'],
    'get_report_content': ['summary_length'],
    'generate_report': ['activity_ids', 'analysis_focus', 'chart_style', 'confirm_mixed', 'data_source', 'dimensions', 'metrics', 'perspective', 'report_theme'],
    'modify_report': ['chart_replacements', 'content_changes', 'free_instruction', 'style_changes'],
    'export_report': ['format', 'output_filename'],
}


def _v3_tool_by_name(name):
    for t in v3_tools.ALL_V3_TOOLS:
        if t.card.name == name:
            return t
    raise AssertionError(f"v3 缺少工具 {name}")


def test_all_expected_tools_have_v3_shell():
    v3_names = {t.card.name for t in v3_tools.ALL_V3_TOOLS}
    for name in _EXPECTED_SCHEMA_FIELDS:
        assert name in v3_names
    assert "write_todos" in v3_names


def test_schema_fields_match_frozen_snapshot():
    for name, expected in _EXPECTED_SCHEMA_FIELDS.items():
        v3_props = set(_v3_tool_by_name(name).card.input_params.get("properties", {}))
        assert v3_props == set(expected), f"{name}: v3={v3_props} 快照={set(expected)}"


def test_card_description_not_truncated():
    """openjiuwen 在 docstring 首个空行截断 description——断言工具使用指引的关键词
    完整出现在 v3 card.description 中（每个工具取 docstring 末尾语义的标志短语）。"""
    sentinels = {
        # docstring 原文：add_to_analysis_queue 末句为“……应直接使用 generate_report 分析已选活动。”
        "add_to_analysis_queue": "generate_report",
        # docstring 原文：generate_report 末句为“……用新参数再次调用本工具。”
        "generate_report": "再次调用",
    }
    for name, phrase in sentinels.items():
        desc = _v3_tool_by_name(name).card.description
        assert phrase in desc, f"{name} 的 description 被截断（缺 {phrase!r}）: {desc!r}"


def test_long_running_tools_have_timeout_override():
    """openjiuwen 默认工具调用 300s 超时；报告生成/修改走 LLM 管线会超过，
    必须经 card.properties['resilience']['timeout_s'] 放宽（联调实测 361s 被杀）。"""
    for name in ("generate_report", "modify_report"):
        card = _v3_tool_by_name(name).card
        assert card.properties["resilience"]["timeout_s"] == 1200.0
    # 其余工具保持默认（不设 resilience 块）
    card = _v3_tool_by_name("search_activities").card
    assert "resilience" not in card.properties
