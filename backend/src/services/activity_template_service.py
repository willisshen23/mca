from __future__ import annotations

import hashlib
import json
import re
from itertools import cycle

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.infrastructure.db.models import ActivityAnalysisTemplate, Base, Skill
from src.infrastructure.db.session import SessionLocal, engine
from src.domain.report.template_skill import merge_template_skill_order


COLORS = [
    {"color": "#165DFF", "bg": "#E8F0FF", "icon": "ti-layout-cards"},
    {"color": "#FF7D00", "bg": "#FFF3E0", "icon": "ti-phone-call"},
    {"color": "#7C3AED", "bg": "#EDE9FE", "icon": "ti-users"},
    {"color": "#009A29", "bg": "#E8FFEA", "icon": "ti-building-bank"},
    {"color": "#0891B2", "bg": "#E0F7FA", "icon": "ti-user-plus"},
    {"color": "#DC2626", "bg": "#FEE2E2", "icon": "ti-shield-check"},
]

DEFAULT_TEMPLATES = [
    {
        "name": "多活动对比分",
        "type": "线上活动",
        "description": "对同类型多个线上活动进行横向对比，找出效果差异与最优实",
        "skills": ["多活动横向对", "活动参与率分", "渠道效果对比", "活动 ROI 分析"],
    },
    {
        "name": "外呼活动分析",
        "type": "通用",
        "description": "面向电话外呼活动，分析接通率、意向度与转化效",
        "skills": ["外呼接通率分析", "客户意向度分", "转化路径分析", "客群行为标签分析"],
    },
    {
        "name": "存量客户激活分",
        "type": "线上活动",
        "description": "针对沉睡客户唤醒活动，分析客群行为、产品偏好与再激活效",
        "skills": ["客群行为标签分析", "产品偏好分析", "活动参与率分", "时间序列趋势分析"],
    },
    {
        "name": "网点活动分析",
        "type": "线下活动",
        "description": "线下网点促销活动的全面效果评估，覆盖客流、转化与成本",
        "skills": ["活动参与率分", "活动 ROI 分析", "客群行为标签分析", "活动成本结构分析"],
    },
]


def ensure_template_database() -> None:
    Base.metadata.create_all(bind=engine)


def template_code_from_name(name: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip().lower()).strip("_")
    digest = hashlib.sha1(name.strip().encode("utf-8")).hexdigest()[:8]
    prefix = (normalized or "template")[:48].strip("_") or "template"
    return f"tpl_{prefix}_{digest}"


def ensure_template_seed_data(db: Session) -> None:
    ensure_template_database()
    if db.query(ActivityAnalysisTemplate).first() is not None:
        return
    color_iter = cycle(COLORS)
    for index, item in enumerate(DEFAULT_TEMPLATES, start=1):
        style = next(color_iter)
        db.add(
            ActivityAnalysisTemplate(
                code=f"{template_code_from_name(item['name'])}_{index}",
                name=item["name"],
                type=item["type"],
                description=item["description"],
                skills_json=json.dumps(item["skills"], ensure_ascii=False),
                icon=style["icon"],
                color=style["color"],
                bg=style["bg"],
                use_count=0,
                status="active",
                is_builtin=True,
            )
        )
    db.commit()


def list_templates(db: Session, template_type: str = "", keyword: str = "") -> list[ActivityAnalysisTemplate]:
    ensure_template_seed_data(db)
    query = db.query(ActivityAnalysisTemplate).filter(ActivityAnalysisTemplate.status == "active")
    if template_type.strip():
        query = query.filter(ActivityAnalysisTemplate.type == template_type.strip())
    if keyword.strip():
        query = query.filter(ActivityAnalysisTemplate.name.contains(keyword.strip()))
    return query.order_by(ActivityAnalysisTemplate.id.asc()).all()


def get_template(db: Session, template_id: int) -> ActivityAnalysisTemplate:
    ensure_template_seed_data(db)
    template = (
        db.query(ActivityAnalysisTemplate)
        .filter(ActivityAnalysisTemplate.id == template_id, ActivityAnalysisTemplate.status == "active")
        .one_or_none()
    )
    if template is None:
        raise ValueError("数据模板不存")
    return template


def get_template_by_code(db: Session, code: str) -> ActivityAnalysisTemplate | None:
    ensure_template_seed_data(db)
    if not code:
        return None
    return (
        db.query(ActivityAnalysisTemplate)
        .filter(ActivityAnalysisTemplate.code == code, ActivityAnalysisTemplate.status == "active")
        .one_or_none()
    )


def create_template(
    db: Session,
    name: str,
    template_type: str,
    description: str,
    skills: list[str],
) -> ActivityAnalysisTemplate:
    ensure_template_seed_data(db)
    clean_name = name.strip()
    clean_type = template_type.strip() or "通用"
    clean_description = description.strip()
    clean_skills = [skill.strip() for skill in skills if skill.strip()]
    if not clean_name:
        raise ValueError("数据模板名称不能为空")
    if not clean_description:
        raise ValueError("数据模板描述不能为空")
    if not clean_skills:
        raise ValueError("数据模板至少需要选择一SKILL")

    count = db.query(ActivityAnalysisTemplate).count()
    style = COLORS[count % len(COLORS)]
    base_code = template_code_from_name(clean_name)
    code = base_code
    suffix = 1
    while db.query(ActivityAnalysisTemplate).filter(ActivityAnalysisTemplate.code == code).one_or_none():
        suffix += 1
        code = f"{base_code}_{suffix}"

    template = ActivityAnalysisTemplate(
        code=code,
        name=clean_name,
        type=clean_type,
        description=clean_description,
        skills_json=json.dumps(clean_skills, ensure_ascii=False),
        icon=style["icon"],
        color=style["color"],
        bg=style["bg"],
        use_count=0,
        status="active",
        is_builtin=False,
    )
    db.add(template)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("数据模板编码重复，请调整数据模板名称") from exc
    db.refresh(template)
    return template


def update_template(
    db: Session,
    template_id: int,
    name: str | None = None,
    template_type: str | None = None,
    description: str | None = None,
    skills: list[str] | None = None,
) -> ActivityAnalysisTemplate:
    template = get_template(db, template_id)
    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("数据模板名称不能为空")
        template.name = clean_name
    if template_type is not None:
        template.type = template_type.strip() or "通用"
    if description is not None:
        clean_description = description.strip()
        if not clean_description:
            raise ValueError("数据模板描述不能为空")
        template.description = clean_description
    if skills is not None:
        clean_skills = [skill.strip() for skill in skills if skill.strip()]
        if not clean_skills:
            raise ValueError("数据模板至少需要选择一SKILL")
        template.skills_json = json.dumps(clean_skills, ensure_ascii=False)
    db.commit()
    db.refresh(template)
    return template


def delete_template(db: Session, template_id: int) -> None:
    template = get_template(db, template_id)
    template.status = "deleted"
    db.commit()


def increment_template_usage(db: Session, template_id: int) -> ActivityAnalysisTemplate:
    template = get_template(db, template_id)
    template.use_count += 1
    db.commit()
    db.refresh(template)
    return template


def increment_template_usage_by_code(code: str) -> ActivityAnalysisTemplate | None:
    if not code:
        return None
    db = SessionLocal()
    try:
        template = get_template_by_code(db, code)
        if template is None:
            return None
        template.use_count += 1
        db.commit()
        db.refresh(template)
        return template
    finally:
        db.close()


def serialize_template(template: ActivityAnalysisTemplate) -> dict:
    try:
        skills = json.loads(template.skills_json or "[]")
    except json.JSONDecodeError:
        skills = []
    return {
        "id": template.id,
        "code": template.code,
        "name": template.name,
        "type": template.type,
        "desc": template.description or "",
        "skills": skills,
        "icon": template.icon,
        "color": template.color,
        "bg": template.bg,
        "useCnt": template.use_count,
        "is_builtin": template.is_builtin,
    }


def serialize_template_for_agent(template: ActivityAnalysisTemplate, db: Session | None = None) -> dict:
    item = serialize_template(template)
    skill_details = _skill_details_for_names(db, item["skills"]) if db is not None else []
    agent_template = {
        **item,
        "template_id": item["code"],
        "template_name": item["name"],
        "template_desc": item["desc"],
        "skill_details": skill_details,
        "scene": "activity_analysis",
        "activity_types": _activity_types_from_template_type(item["type"]),
        "source": "activity_template_management",
    }
    return merge_template_skill_order(agent_template)


def list_agent_activity_templates(template_type: str = "", keyword: str = "") -> list[dict]:
    db = SessionLocal()
    try:
        return [
            serialize_template_for_agent(template, db)
            for template in list_templates(db, template_type=template_type, keyword=keyword)
        ]
    finally:
        db.close()


def _skill_details_for_names(db: Session, skill_names: list[str]) -> list[dict]:
    names = [str(name or "").strip() for name in skill_names if str(name or "").strip()]
    if not names:
        return []

    skills = (
        db.query(Skill)
        .filter(Skill.status == "active", Skill.name.in_(names))
        .all()
    )
    skill_by_name = {skill.name: skill for skill in skills}
    details: list[dict] = []
    for name in names:
        skill = skill_by_name.get(name)
        if skill is None:
            details.append(
                {
                    "name": name,
                    "skill_name": name,
                    "skill_description": "",
                    "skill_template_preview": "",
                    "skill_category": "",
                }
            )
            continue
        details.append(
            {
                "id": skill.id,
                "code": skill.code,
                "name": skill.name,
                "skill_name": skill.name,
                "skill_description": skill.description or "",
                "skill_template_preview": skill.template or "",
                "skill_category": skill.category.name if skill.category else "",
                "version": skill.version,
            }
        )
    return details


def _activity_types_from_template_type(template_type: str) -> list[str]:
    if template_type == "线上活动":
        return ["online"]
    if template_type == "线下活动":
        return ["offline"]
    return ["online", "offline"]
