from __future__ import annotations

import json
import logging

from src.report_pipeline.state import AgentState

logger = logging.getLogger("activity-analysis.agent")


async def uploaded_component_value_extract_node(state: AgentState) -> dict:
    dataset = state.get("uploaded_activity_dataset") or {}
    if not dataset:
        return {"next_agent": "finalize", "final_response": "Uploaded activity data is not normalized."}

    data_summary = _safe_json_loads(state.get("data_summary") or "")
    activity_template_match = state.get("activity_template_match_result") or {}
    component_values = {
        "component_values": {
            "uploaded_activity_data": {
                "source": "uploaded_file",
                "file_name": dataset.get("file_name", ""),
                "total_rows": dataset.get("total_rows", 0),
                "headers": dataset.get("headers", []),
                "activities": dataset.get("activities", []),
                "sample_records": dataset.get("sample_records", []),
                "basic_stats": data_summary.get("basic_stats", {}) if isinstance(data_summary, dict) else {},
                "missing_values": data_summary.get("missing_values", {}) if isinstance(data_summary, dict) else {},
                "numeric_columns": data_summary.get("numeric_columns", []) if isinstance(data_summary, dict) else [],
            }
        },
        "activity_template_match": _compact_activity_template(activity_template_match),
        "report_sections": _activity_template_sections(activity_template_match),
        "source": "uploaded_file",
    }
    logger.info(
        "uploaded_component_value_extract completed: rows=%s columns=%d",
        dataset.get("total_rows", 0),
        len(dataset.get("headers") or []),
    )
    logger.debug("uploaded_component_value_extract data: %s", component_values)
    return {
        "component_value_params": {
            "source": "uploaded_file",
            "file_name": dataset.get("file_name", ""),
            "activity_template_match": _compact_activity_template(activity_template_match),
        },
        "component_values": component_values,
        "next_agent": "supervisor",
    }


def _compact_activity_template(match_result: dict) -> dict:
    if not isinstance(match_result, dict):
        return {}
    return {
        "template_id": match_result.get("template_id", ""),
        "template_name": match_result.get("template_name", ""),
        "activity_ids": match_result.get("activity_ids", []),
        "skill_sequence": match_result.get("skill_sequence", []),
        "dependent_components": match_result.get("dependent_components", []),
    }


def _activity_template_sections(match_result: dict) -> list:
    if not isinstance(match_result, dict):
        return []
    sections = match_result.get("report_sections")
    if isinstance(sections, list):
        return sections
    skill_sequence = match_result.get("skill_sequence") or []
    return [
        {"position": index + 1, "skill_name": skill}
        for index, skill in enumerate(skill_sequence)
    ]


def _safe_json_loads(text: str):
    try:
        return json.loads(text)
    except Exception:
        return {}
