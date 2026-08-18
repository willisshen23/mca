from __future__ import annotations

import re
import hashlib
from typing import Any


SKILL_COMPONENT_RULES = [
    ("外呼接通", "outbound_connect_rate", ["call_count", "connected_count", "connect_rate"]),
    ("客户意向", "customer_intent", ["intent_customer_count", "high_intent_ratio", "conversion_rate"]),
    ("转化路径", "conversion_path", ["exposure_count", "click_count", "conversion_count", "conversion_rate"]),
    ("渠道效果", "channel_effect", ["channel_count", "conversion_rate", "roi"]),
    ("ROI", "asset_growth", ["financial_asset_increase", "deposit_increase", "app_transaction_active_rate"]),
    ("成本结构", "asset_growth", ["financial_asset_increase", "deposit_increase", "app_transaction_active_rate"]),
    ("资产", "asset_growth", ["financial_asset_increase", "deposit_increase", "wealth_increase"]),
    ("客群", "customer_value", ["valuable_customers", "valuable_customer_ratio", "converted_valuable_customers"]),
    ("客户价值", "customer_value", ["valuable_customers", "valuable_customer_ratio", "converted_valuable_customers"]),
    ("产品偏好", "customer_value", ["valuable_customers", "valuable_customer_ratio", "converted_valuable_customers"]),
    ("风险", "customer_value", ["valuable_customers", "lost_valuable_customers", "valuable_customer_ratio"]),
    ("趋势", "overview", ["participant_count", "avg_aum", "status_distribution"]),
    ("参与", "overview", ["participant_count", "conversion_rate", "status_distribution"]),
    ("多活动", "overview", ["activity_count", "participant_count", "avg_aum"]),
    ("概览", "overview", ["activity_count", "participant_count", "status_distribution"]),
]
DEFAULT_METRICS = ["activity_count", "participant_count", "conversion_rate"]

# display_requirement（SKILL 模板预览）脱敏：
# 模板预览的「输出示例」中含大量具体示例数值/产品名，原样进入报告生成提示词后，
# 模型在 report_data 缺少对应数据时会照抄示例值。这里保留示例的章节标题与表头结构，
# 剥离全部示例数据行并将示例段落中的数字掩码为 X。
_EXAMPLE_MARKER_RE = re.compile(r"^\s*#{1,6}\s*输出示例[:：]?\s*$")
# 示例区块只在「列首要求条目」（行首 - 开头、非占位/加粗条目）处结束；
# 示例内部的子条目要么缩进、要么以 -【 或 - ** 开头，不会误判。
_EXAMPLE_END_BULLET_RE = re.compile(r"^-\s+(?![【*])")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s*\S")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|?\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
_NUMBER_RE = re.compile(r"[0-9]+(?:[,.][0-9]+)*")
_EXAMPLE_PLACEHOLDER_CELL = "（示例数值略）"


def sanitize_display_requirement(preview: str) -> str:
    """剥离模板预览「输出示例」中的示例数值，保留结构指引。

    - Markdown 表格：保留表头与分隔行，数据行整体替换为一行占位行
      （示例表格中的具体数值、产品名、机构名均随数据行移除）。
    - 示例区块内的普通文字行：数字掩码为 X（章节标题行原样保留）。
    - 示例区块之外的要求正文（InputFormat/OutputFormat/Constrains 等）不动，
      其中的业务口径数字（如“30秒”“100万”）完整保留。
    """
    if not preview:
        return ""

    sanitized: list[str] = []
    in_example = False
    table_header_cols = 0
    table_seen_separator = False
    table_stripped_rows = 0

    def flush_table_placeholder() -> None:
        nonlocal table_header_cols, table_seen_separator, table_stripped_rows
        if table_header_cols and table_stripped_rows:
            placeholder = "|" + "|".join([_EXAMPLE_PLACEHOLDER_CELL] * table_header_cols) + "|"
            sanitized.append(placeholder)
        table_header_cols = 0
        table_seen_separator = False
        table_stripped_rows = 0

    for line in str(preview).splitlines():
        if _EXAMPLE_MARKER_RE.match(line):
            flush_table_placeholder()
            in_example = True
            sanitized.append(line)
            continue
        if in_example and _EXAMPLE_END_BULLET_RE.match(line):
            flush_table_placeholder()
            in_example = False
            sanitized.append(line)
            continue

        if _TABLE_ROW_RE.match(line) and "|" in line:
            if _TABLE_SEPARATOR_RE.match(line):
                if table_header_cols:
                    table_seen_separator = True
                    sanitized.append(line)
                else:
                    sanitized.append(line)
                continue
            if not table_header_cols:
                table_header_cols = max(line.count("|") - 1, 1)
                # 表头单元格也可能嵌入示例数值（如“存款（购买46人）”），统一掩码；
                # 其中的口径数字（如“3日”）在要求正文中均有说明，掩码不影响理解。
                sanitized.append(_NUMBER_RE.sub("X", line) if in_example else line)
                continue
            table_stripped_rows += 1
            continue

        flush_table_placeholder()
        if in_example and not _HEADING_RE.match(line):
            sanitized.append(_NUMBER_RE.sub("X", line))
        else:
            sanitized.append(line)

    flush_table_placeholder()
    return "\n".join(sanitized)


def normalize_template_skill_sequence(template: dict[str, Any]) -> list[str]:
    for key in ("skill_sequence", "skills", "skillSequence", "skill_components", "skillComponents"):
        sequence = _extract_skill_names(template.get(key))
        if sequence:
            return sequence

    dependent_components = template.get("dependent_components")
    sequence = _extract_skill_names(dependent_components)
    if sequence:
        return sequence
    return []


def build_dependent_components_from_skills(
    skills: list[str],
    skill_details: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    detail_by_name = _skill_detail_map(skill_details or [])
    for index, skill_name in enumerate(skills, start=1):
        component_id, metrics = component_for_skill(skill_name)
        detail = detail_by_name.get(skill_name, {})
        components.append(
            {
                "position": index,
                "component_id": component_id,
                "name": skill_name,
                "skill_name": skill_name,
                "display_name": skill_name,
                "skill_description": detail.get("skill_description") or detail.get("description") or "",
                "skill_template_preview": detail.get("skill_template_preview") or detail.get("template") or detail.get("tpl") or "",
                "skill_category": detail.get("skill_category") or detail.get("cat") or "",
                "metrics": metrics,
            }
        )
    return components


def merge_template_skill_order(template: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(template)
    skill_sequence = normalize_template_skill_sequence(normalized)
    skill_details = normalized.get("skill_details") if isinstance(normalized.get("skill_details"), list) else []
    if skill_sequence:
        normalized["skill_sequence"] = skill_sequence
        normalized["skills"] = skill_sequence
        normalized["dependent_components"] = build_dependent_components_from_skills(skill_sequence, skill_details)
        normalized["component_ids"] = unique_ordered(
            component["component_id"] for component in normalized["dependent_components"]
        )
    elif normalized.get("dependent_components"):
        normalized["dependent_components"] = _normalize_dependent_components(normalized["dependent_components"])
        normalized["skill_sequence"] = [
            component.get("skill_name") or component.get("name") or component.get("component_id")
            for component in normalized["dependent_components"]
        ]
        normalized["component_ids"] = unique_ordered(
            component.get("component_id") for component in normalized["dependent_components"]
        )
    return normalized


def apply_template_skill_order(
    match_result: dict[str, Any],
    templates: list[dict[str, Any]],
    activities: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_match = dict(match_result)
    matched_template = find_matched_template(templates, normalized_match)
    source = merge_template_skill_order(matched_template or normalized_match)
    skill_sequence = normalize_template_skill_sequence(source)
    skill_details = source.get("skill_details") if isinstance(source.get("skill_details"), list) else []

    if skill_sequence:
        dependent_components = build_dependent_components_from_skills(skill_sequence, skill_details)
    else:
        dependent_components = _normalize_dependent_components(
            normalized_match.get("dependent_components") or source.get("dependent_components") or []
        )
        skill_sequence = [
            component.get("skill_name") or component.get("name") or component.get("component_id")
            for component in dependent_components
        ]

    template_id = _first_text(
        source.get("template_id"),
        source.get("code"),
        source.get("id"),
        normalized_match.get("template_id"),
    )
    template_name = _first_text(
        source.get("template_name"),
        source.get("name"),
        normalized_match.get("template_name"),
    )
    activity_ids = unique_ordered(normalized_match.get("activity_ids", [])) or _activity_ids(activities)

    normalized_match.update(
        {
            "template_id": template_id,
            "template_name": template_name,
            "activity_ids": activity_ids,
            "skill_details": skill_details,
            "skill_sequence": skill_sequence,
            "dependent_components": dependent_components,
            "component_ids": unique_ordered(
                component.get("component_id") for component in dependent_components
            ),
            "report_section_order": [
                {
                    "position": component.get("position", index),
                    "skill_name": component.get("skill_name") or component.get("name"),
                    "component_id": component.get("component_id"),
                    "metrics": component.get("metrics", []),
                    "skill_description": component.get("skill_description", ""),
                    "skill_template_preview": component.get("skill_template_preview", ""),
                    "skill_category": component.get("skill_category", ""),
                }
                for index, component in enumerate(dependent_components, start=1)
            ],
        }
    )
    return normalized_match


def build_report_sections(match_result: dict[str, Any], component_values: dict[str, Any]) -> list[dict[str, Any]]:
    values = unwrap_component_values(component_values)
    dependent_components = _normalize_dependent_components(match_result.get("dependent_components") or [])
    if not dependent_components:
        dependent_components = build_dependent_components_from_skills(
            normalize_template_skill_sequence(match_result)
        )

    sections = []
    for index, component in enumerate(dependent_components, start=1):
        component_id = component.get("component_id", "")
        sections.append(
            {
                "position": component.get("position", index),
                "skill_name": component.get("skill_name") or component.get("name") or component_id,
                "component_id": component_id,
                "metrics": component.get("metrics", []),
                "skill_description": component.get("skill_description", ""),
                "skill_template_preview": component.get("skill_template_preview", ""),
                "skill_category": component.get("skill_category", ""),
                "display_requirement": component.get("skill_template_preview", ""),
                "values": values.get(component_id, {}),
            }
        )
    return sections


def unwrap_component_values(component_values: dict[str, Any]) -> dict[str, Any]:
    if isinstance(component_values, dict) and isinstance(component_values.get("component_values"), dict):
        return component_values["component_values"]
    return component_values if isinstance(component_values, dict) else {}


def component_for_skill(skill_name: str) -> tuple[str, list[str]]:
    normalized = str(skill_name or "")
    for keyword, component_id, metrics in SKILL_COMPONENT_RULES:
        if keyword.lower() in normalized.lower():
            return component_id, metrics
    return slug_component_id(normalized), DEFAULT_METRICS


def slug_component_id(value: str) -> str:
    ascii_slug = re.sub(r"[^0-9a-zA-Z]+", "_", value.strip().lower()).strip("_")
    if ascii_slug:
        return ascii_slug[:48]
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"skill_{digest}"


def unique_ordered(values) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def find_matched_template(templates: list[dict[str, Any]], match_result: dict[str, Any]) -> dict[str, Any] | None:
    candidates = {
        str(match_result.get("template_id") or "").strip(),
        str(match_result.get("template_name") or "").strip(),
    }
    candidates.discard("")
    for template in templates:
        values = {
            str(template.get("template_id") or "").strip(),
            str(template.get("code") or "").strip(),
            str(template.get("id") or "").strip(),
            str(template.get("template_name") or "").strip(),
            str(template.get("name") or "").strip(),
        }
        if candidates & values:
            return template
    return None


def _skill_detail_map(skill_details: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for detail in skill_details:
        if not isinstance(detail, dict):
            continue
        name = _first_text(detail.get("skill_name"), detail.get("name"))
        if name:
            result[name] = detail
    return result


def _normalize_dependent_components(components: list[Any]) -> list[dict[str, Any]]:
    normalized = []
    for index, component in enumerate(components or [], start=1):
        if isinstance(component, dict):
            skill_name = _first_text(component.get("skill_name"), component.get("name"), component.get("title"))
            component_id = _first_text(component.get("component_id"), component.get("id"))
            if not component_id and skill_name:
                component_id, _ = component_for_skill(skill_name)
            metrics = component.get("metrics") if isinstance(component.get("metrics"), list) else []
            normalized.append(
                {
                    **component,
                    "position": int(component.get("position") or index),
                    "component_id": component_id,
                    "name": skill_name or component_id,
                    "skill_name": skill_name or component_id,
                    "skill_description": component.get("skill_description", ""),
                    "skill_template_preview": component.get("skill_template_preview", ""),
                    "skill_category": component.get("skill_category", ""),
                    "metrics": metrics,
                }
            )
        else:
            skill_name = str(component or "").strip()
            if skill_name:
                component_id, metrics = component_for_skill(skill_name)
                normalized.append(
                    {
                        "position": index,
                        "component_id": component_id,
                        "name": skill_name,
                        "skill_name": skill_name,
                        "metrics": metrics,
                    }
                )
    return sorted(normalized, key=lambda item: item.get("position", 0))


def _extract_skill_names(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，\n;；]+", value) if item.strip()]
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = _first_text(item.get("skill_name"), item.get("name"), item.get("title"), item.get("component_id"))
            else:
                text = str(item or "").strip()
            if text:
                names.append(text)
        return names
    return []


def _activity_ids(activities: list[dict[str, Any]]) -> list[str]:
    return unique_ordered(
        activity.get("activity_id") or activity.get("act_no") or activity.get("活动编号")
        for activity in activities
    )


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""
