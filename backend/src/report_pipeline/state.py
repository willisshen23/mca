"""Shared agent state schema.

This module is intentionally kept small: it defines the contract exchanged by
the supervisor and all worker agents. Agent logic should live under
``src.agent.capabilities``; graph construction and routing should live in sibling graph
modules.
"""

from __future__ import annotations

from typing import TypedDict


class AnalysisComponentConfig(TypedDict, total=False):
    id: str
    type: str
    title: str
    config: dict


class AnalysisFramework(TypedDict, total=False):
    title: str
    components: list[AnalysisComponentConfig]
    report_config: dict


class AgentState(TypedDict, total=False):
    # 运行时本就是 plain dict 列表（v3 消息均为 dict）
    messages: list[dict]

    request_id: str
    plan_request_id: str
    thread_id: str
    user_name: str
    original_user_text: str
    workflow_key: str
    workflow_name: str
    workflow_stage: str
    report_context: dict

    uploaded_file_path: str
    file_preview: str
    uploaded_activity_dataset: dict

    analysis_framework: AnalysisFramework

    data_summary: str
    per_component_results: dict
    html_report: str
    target_format: str
    formatted_output_path: str
    validation_result: str
    report_html_guard_result: dict
    report_html_guard_retry_count: int
    report_html_guard_retry_requested: bool
    report_html_guard_retry_step: str

    marketing_intent: dict
    activity_query_params: dict
    activity_list: list[dict]
    awaiting_activity_selection: bool
    selected_activity_ids: list[str]
    selected_report_activity_ids: list[str]
    report_history_enabled: bool
    activity_route_result: dict
    workflow_mode: str
    outbound_activity_data: dict
    outbound_activity_data_found: bool
    template_list: list[dict]
    template_match_result: dict
    matched_data_templates: list[dict]
    component_value_params: dict
    component_values: dict
    component_value_cleanup_result: dict
    branch_drilldown_result: dict
    activity_template_list: list[dict]
    activity_template_match_result: dict

    user_id: str
    org_no: str
    channel: str

    next_agent: str
    final_response: str

    plan: list[dict]
