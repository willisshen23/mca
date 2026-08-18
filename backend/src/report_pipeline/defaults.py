from __future__ import annotations

from src.report_pipeline.state import AgentState


REPORT_CONTEXT_KEYWORDS = (
    "校验",
    "验证",
    "检查报",
    "下载",
    "导出",
    "转换",
    "转化",
    "不满",
    "重新生成",
    "重生",
    "再生",
    "换个",
    "更换",
    "调整",
    "改一",
    "组件模板",
    "活动模板",
)


RUNTIME_STATE_DEFAULTS = {
    "plan": [],
    "workflow_key": "",
    "workflow_name": "",
    "workflow_stage": "",
    "report_context": {},
    "final_response": "",
    "marketing_intent": {},
    "activity_query_params": {},
    "activity_list": [],
    "uploaded_activity_dataset": {},
    "awaiting_activity_selection": False,
    "selected_activity_ids": [],
    "selected_report_activity_ids": [],
    "report_history_enabled": False,
    "activity_route_result": {},
    "workflow_mode": "",
    "outbound_activity_data": {},
    "outbound_activity_data_found": False,
    "outbound_activity_data_map": {},
    "perspective_key": "",
    "perspective_keyword": "",
    "template_list": [],
    "template_match_result": {},
    "matched_data_templates": [],
    "component_value_params": {},
    "component_values": {},
    "component_value_cleanup_result": {},
    "html_report": "",
    "report_html_guard_result": {},
    "report_html_guard_retry_count": 0,
    "report_html_guard_retry_requested": False,
    "report_html_guard_retry_step": "",
    "formatted_output_path": "",
    "validation_result": "",
    "per_component_results": {},
}


def is_new_user_request(state: AgentState) -> bool:
    request_id = state.get("request_id", "")
    plan_request_id = state.get("plan_request_id", "")
    return bool(request_id and request_id != plan_request_id)


def should_preserve_report_context(user_text: str) -> bool:
    normalized = user_text.strip().lower()
    return any(keyword in normalized for keyword in REPORT_CONTEXT_KEYWORDS)


def reset_runtime_for_new_request(state: AgentState) -> AgentState:
    return {
        **state,
        **RUNTIME_STATE_DEFAULTS,
    }
