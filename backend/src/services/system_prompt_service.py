from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from src.infrastructure.db.models import Base, SystemPrompt
from src.infrastructure.db.session import SessionLocal, engine

logger = logging.getLogger("activity-analysis.agent")

PUBLISHED = "published"
PENDING = "pending"


def ensure_system_prompt_database() -> None:
    Base.metadata.create_all(bind=engine)


def ensure_default_system_prompts(db: Session) -> None:
    ensure_system_prompt_database()
    for item in _default_prompt_definitions():
        existing = get_prompt_by_key(db, item["prompt_key"], ensure_defaults=False)
        if existing is not None:
            _sync_default_prompt_if_needed(existing, item)
            continue
        prompt = SystemPrompt(
            prompt_key=item["prompt_key"],
            prompt_name=item["prompt_name"],
            agent_name=item["agent_name"],
            scenario=item["scenario"],
            content=item["content"],
            published_content=item["content"],
            variables_json=json.dumps(item["variables"], ensure_ascii=False),
            status=PUBLISHED,
            is_active=True,
            created_by="system",
            updated_by="system",
        )
        db.add(prompt)
    db.commit()


def _sync_default_prompt_if_needed(prompt: SystemPrompt, default_item: dict[str, Any]) -> None:
    if prompt.prompt_key != "component_value_param":
        return
    default_content = default_item["content"]
    default_variables = json.dumps(default_item["variables"], ensure_ascii=False)
    if "{activities}" in (prompt.content or "") and prompt.variables_json == default_variables:
        return

    prompt.content = default_content
    prompt.published_content = default_content
    prompt.variables_json = default_variables
    prompt.status = PUBLISHED
    prompt.is_active = True
    prompt.updated_by = "system"
    logger.info("system_prompt default synced prompt_key=%s", prompt.prompt_key)


def list_system_prompts(db: Session, status: str = "", keyword: str = "") -> list[SystemPrompt]:
    ensure_default_system_prompts(db)
    query = db.query(SystemPrompt)
    clean_status = _normalize_status(status, allow_empty=True)
    if clean_status:
        query = query.filter(SystemPrompt.status == clean_status)
    if keyword.strip():
        word = keyword.strip()
        query = query.filter(
            SystemPrompt.prompt_name.contains(word)
            | SystemPrompt.prompt_key.contains(word)
            | SystemPrompt.agent_name.contains(word)
        )
    return query.order_by(SystemPrompt.id.asc()).all()


def get_prompt(db: Session, prompt_id: int) -> SystemPrompt:
    ensure_default_system_prompts(db)
    prompt = db.query(SystemPrompt).filter(SystemPrompt.id == prompt_id).one_or_none()
    if prompt is None:
        raise ValueError("系统提示词不存在")
    return prompt


def get_prompt_by_key(
    db: Session,
    prompt_key: str,
    *,
    ensure_defaults: bool = True,
) -> SystemPrompt | None:
    if ensure_defaults:
        ensure_default_system_prompts(db)
    clean_key = prompt_key.strip()
    if not clean_key:
        return None
    return db.query(SystemPrompt).filter(SystemPrompt.prompt_key == clean_key).one_or_none()


def create_system_prompt(
    db: Session,
    *,
    prompt_key: str,
    prompt_name: str,
    agent_name: str,
    scenario: str,
    content: str,
    variables: list[str],
    status: str = PENDING,
) -> SystemPrompt:
    ensure_default_system_prompts(db)
    clean_key = prompt_key.strip()
    if not clean_key:
        raise ValueError("提示key 不能为空")
    if get_prompt_by_key(db, clean_key, ensure_defaults=False) is not None:
        raise ValueError("提示key 已存")

    clean_status = _normalize_status(status)
    prompt = SystemPrompt(
        prompt_key=clean_key,
        prompt_name=_required(prompt_name, "提示词名称不能为"),
        agent_name=_required(agent_name, "Agent 不能为空"),
        scenario=scenario.strip(),
        content=_required(content, "提示词内容不能为"),
        published_content=content if clean_status == PUBLISHED else None,
        variables_json=json.dumps(_normalize_variables(variables), ensure_ascii=False),
        status=clean_status,
        is_active=clean_status == PUBLISHED,
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt


def update_system_prompt(
    db: Session,
    prompt_id: int,
    *,
    prompt_name: str | None = None,
    agent_name: str | None = None,
    scenario: str | None = None,
    content: str | None = None,
    variables: list[str] | None = None,
) -> SystemPrompt:
    prompt = get_prompt(db, prompt_id)
    if prompt_name is not None:
        prompt.prompt_name = _required(prompt_name, "提示词名称不能为")
    if agent_name is not None:
        prompt.agent_name = _required(agent_name, "Agent 不能为空")
    if scenario is not None:
        prompt.scenario = scenario.strip()
    if content is not None:
        prompt.content = _required(content, "提示词内容不能为")
    if variables is not None:
        prompt.variables_json = json.dumps(_normalize_variables(variables), ensure_ascii=False)

    prompt.status = PENDING
    prompt.is_active = False
    db.commit()
    db.refresh(prompt)
    return prompt


def publish_system_prompt(db: Session, prompt_id: int) -> SystemPrompt:
    prompt = get_prompt(db, prompt_id)
    prompt.published_content = prompt.content
    prompt.status = PUBLISHED
    prompt.is_active = True
    db.commit()
    db.refresh(prompt)
    return prompt


def get_runtime_prompt(prompt_key: str, fallback_content: str) -> str:
    db = SessionLocal()
    try:
        prompt = get_prompt_by_key(db, prompt_key)
        if prompt is None:
            return _ensure_runtime_prompt_rules(prompt_key, fallback_content)
        if prompt.status == PUBLISHED and prompt.content.strip():
            return _ensure_runtime_prompt_rules(prompt_key, prompt.content)
        if (prompt.published_content or "").strip():
            return _ensure_runtime_prompt_rules(prompt_key, prompt.published_content or fallback_content)
        return _ensure_runtime_prompt_rules(prompt_key, fallback_content)
    except Exception as exc:
        logger.warning("system_prompt runtime fallback prompt_key=%s error=%s", prompt_key, str(exc))
        return _ensure_runtime_prompt_rules(prompt_key, fallback_content)
    finally:
        db.close()


def _ensure_runtime_prompt_rules(prompt_key: str, content: str) -> str:
    if prompt_key != "marketing_report_synthesis":
        return content
    if "章节可生成性判断" not in content:
        content = content.rstrip() + """

## 运行时强制规则：章节可生成性判断
- `report_sections` 只表示活动报告模板的候选章节和展示要求，不代表所有章节都必须生成。
- 生成每个章节前，必须判断该章节要求是否能在 `report_data` 中找到可支撑的数据。
- 完全找不到对应数据，或只有空字符串、null、空数组、空对象、无关字段的章节，必须跳过。
- 只有部分数据可支撑时，只生成可支撑的子内容；无法匹配的数据维度、图表、表格、指标、结论一律不生成。
- 禁止为补齐模板而生成空表、空图、占位段落、泛泛分析或“暂无数据”章节。
- 数值 `0` 是有效数据；空字符串、null、空数组、空对象才视为不可用数据。
- 不要在报告末尾输出“报告生成时间”“数据来源”“仅供内部参考”等页脚、尾注或免责声明。
- `display_requirement` 和 SKILL 模板预览只能作为内部生成指令，禁止把其中的原文、可视化建议、图表建议、展示建议、字段说明、输出要求直接复制到报告正文。
- 报告正文不要出现“可视化建议：”“图表建议：”“建议使用柱状图/折线图”“本章节应展示/需要展示”等模板说明性措辞。
"""
    if "指标卡片排版规范" not in content:
        content = content.rstrip() + """

## 运行时强制规则：指标卡片排版规范
- 同一模块（同一章节）内的所有指标卡片必须放进同一个卡片容器中，禁止按每行 N 个手动拆分成多个行容器。
- 卡片容器统一使用 CSS Grid：display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:16px; 禁止使用 flex 百分比宽度手动换行。
- 同一容器内的卡片必须等宽等高；最后一行不足一整行时，剩余卡片保持与其他卡片相同宽度并靠左排列，禁止单独拉满整行或居中独占一行。
- 同一行并排的卡片（如对比卡片、结论卡片）必须均分整行宽度：使用 display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:16px; 或给每张卡片设置 flex:1，禁止给卡片设置固定像素宽度导致行右侧大面积留白。
- 指标卡片与图表分区排列：图表容器独占整行（width:100%），不要与指标卡片混排在同一行内。
- 同一章节内多个图表纵向排列、各占整行；确需并排对比时使用 display:grid; grid-template-columns:repeat(auto-fit, minmax(360px, 1fr)); gap:16px; 保证图表等宽。
- 表格宽度占满父容器（width:100%），同一报告内表格样式保持一致。
"""
    return content


def format_runtime_prompt(prompt_key: str, fallback_content: str, **values: Any) -> str:
    prompt_template = get_runtime_prompt(prompt_key, fallback_content)
    if prompt_key == "component_value_param" and "{activities}" not in prompt_template:
        logger.info("system_prompt using fallback for component_value_param because activities variable is missing")
        prompt_template = fallback_content
    try:
        return prompt_template.format(**values)
    except Exception as exc:
        logger.warning(
            "system_prompt format failed prompt_key=%s fallback_default error=%s",
            prompt_key,
            str(exc),
        )
        return fallback_content.format(**values)


def serialize_system_prompt(prompt: SystemPrompt) -> dict[str, Any]:
    variables = _decode_variables(prompt.variables_json)
    missing_variables = validate_prompt_variables(prompt.content, variables)
    return {
        "id": prompt.id,
        "prompt_key": prompt.prompt_key,
        "prompt_name": prompt.prompt_name,
        "agent_name": prompt.agent_name,
        "scenario": prompt.scenario,
        "content": prompt.content,
        "variables": variables,
        "status": prompt.status,
        "is_active": prompt.is_active,
        "missing_variables": missing_variables,
        "updated_at": prompt.updated_at.isoformat() if prompt.updated_at else "",
        "created_at": prompt.created_at.isoformat() if prompt.created_at else "",
    }


def validate_prompt_variables(content: str, variables: list[str]) -> list[str]:
    return [name for name in _normalize_variables(variables) if f"{{{name}}}" not in content]


def _default_prompt_definitions() -> list[dict[str, Any]]:
    from src.report_pipeline.prompts.marketing_workflow import (
        ACTIVITY_TEMPLATE_MATCHING_PROMPT,
        COMPONENT_VALUE_PARAM_PROMPT,
        MARKETING_REPORT_SYNTHESIS_PROMPT,
        TEMPLATE_MATCHING_PROMPT,
    )

    return [
        {
            "prompt_key": "marketing_report_synthesis",
            "prompt_name": "活动报告生成提示",
            "agent_name": "report_generation",
            "scenario": "activity_report",
            "content": MARKETING_REPORT_SYNTHESIS_PROMPT,
            "variables": [
                "user_text",
                "intent",
                "activities",
                "data_template_match",
                "activity_template_match",
                "report_sections",
                "report_data",
            ],
        },
        {
            "prompt_key": "activity_template_matching",
            "prompt_name": "活动报告模板匹配提示",
            "agent_name": "report_generation",
            "scenario": "activity_template",
            "content": ACTIVITY_TEMPLATE_MATCHING_PROMPT,
            "variables": [
                "activities",
                "data_template_match",
                "component_values",
                "activity_templates",
            ],
        },
        {
            "prompt_key": "template_matching",
            "prompt_name": "数据模板相似度匹配提示词",
            "agent_name": "data_analysis",
            "scenario": "data_template",
            "content": TEMPLATE_MATCHING_PROMPT,
            "variables": ["user_text","intent", "activities", "templates"],
        },
        {
            "prompt_key": "component_value_param",
            "prompt_name": "组件指标参数生成提示",
            "agent_name": "data_analysis",
            "scenario": "component_value",
            "content": COMPONENT_VALUE_PARAM_PROMPT,
            "variables": ["match_result", "activities", "intent"],
        },
    ]


def _decode_variables(raw: str) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        value = []
    return _normalize_variables(value if isinstance(value, list) else [])


def _normalize_variables(variables: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in variables:
        text = str(value or "").strip()
        if not text:
            continue
        text = re.sub(r"^\{|\}$", "", text)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _normalize_status(status: str, *, allow_empty: bool = False) -> str:
    clean = str(status or "").strip().lower()
    if clean == "all":
        clean = ""
    if allow_empty and not clean:
        return ""
    if clean not in {PUBLISHED, PENDING}:
        raise ValueError("状态仅支持 published 或 pending")
    return clean


def _required(value: str, message: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(message)
    return text
