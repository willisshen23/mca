from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.infrastructure.db.models import Base, Skill, SkillCategory, SkillUsageLog
from src.infrastructure.db.seed import seed_default_skills
from src.infrastructure.db.session import SessionLocal, engine

logger = logging.getLogger("njbank.agent")


def ensure_skill_database() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_skill_usage_schema()


def ensure_skill_usage_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    if "skills" in table_names:
        skill_columns = {column["name"] for column in inspector.get_columns("skills")}
        if "use_count" not in skill_columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE skills ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0"))
            logger.info("skills schema upgraded: added column use_count")

    if "skill_usage_logs" not in table_names:
        return

    existing_columns = {column["name"] for column in inspector.get_columns("skill_usage_logs")}
    missing_columns = {
        "request_id": "VARCHAR(64)",
        "source_type": "VARCHAR(40)",
        "source_id": "VARCHAR(80)",
        "source_code": "VARCHAR(120)",
    }
    with engine.begin() as conn:
        for column_name, column_type in missing_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(text(f"ALTER TABLE skill_usage_logs ADD COLUMN {column_name} {column_type}"))
            logger.info("skill_usage_logs schema upgraded: added column %s", column_name)


def ensure_seed_data(db: Session) -> None:
    ensure_skill_database()
    if db.query(Skill).first() is None:
        seed_default_skills(db)


def category_code_from_name(name: str) -> str:
    return "cat_" + "_".join(name.strip().lower().split())


def skill_code_from_name(name: str) -> str:
    return "skill_" + "_".join(name.strip().lower().split())


def list_categories(db: Session) -> list[SkillCategory]:
    ensure_seed_data(db)
    return (
        db.query(SkillCategory)
        .filter(SkillCategory.is_enabled.is_(True))
        .order_by(SkillCategory.sort_order.asc(), SkillCategory.id.asc())
        .all()
    )


def create_category(db: Session, name: str, description: str = "") -> SkillCategory:
    ensure_seed_data(db)
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("分类名称不能为空")
    exists = db.query(SkillCategory).filter(SkillCategory.name == clean_name).one_or_none()
    if exists:
        return exists
    max_sort = max((category.sort_order for category in list_categories(db)), default=0)
    category = SkillCategory(
        code=category_code_from_name(clean_name),
        name=clean_name,
        description=description.strip() or None,
        sort_order=max_sort + 1,
        is_enabled=True,
    )
    db.add(category)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        category.code = f"{category.code}_{max_sort + 1}"
        db.add(category)
        db.commit()
    db.refresh(category)
    return category


def list_skills(db: Session, category_id: int | None = None, keyword: str = "") -> list[Skill]:
    ensure_seed_data(db)
    query = db.query(Skill).join(SkillCategory).filter(Skill.status == "active")
    if category_id:
        query = query.filter(Skill.category_id == category_id)
    if keyword.strip():
        query = query.filter(Skill.name.contains(keyword.strip()))
    return query.order_by(Skill.sort_order.asc(), Skill.id.asc()).all()


def resolve_category(
    db: Session,
    category_id: int | None = None,
    category_name: str = "",
) -> SkillCategory:
    ensure_seed_data(db)
    category = None
    if category_id:
        category = (
            db.query(SkillCategory)
            .filter(SkillCategory.id == category_id, SkillCategory.is_enabled.is_(True))
            .one_or_none()
        )
    if category is None and category_name.strip():
        category = (
            db.query(SkillCategory)
            .filter(SkillCategory.name == category_name.strip(), SkillCategory.is_enabled.is_(True))
            .one_or_none()
        )
    if category is None:
        raise ValueError("请选择有效SKILL 分类")
    return category


def create_skill(
    db: Session,
    name: str,
    template: str,
    category_id: int | None = None,
    category_name: str = "",
    description: str = "",
) -> Skill:
    ensure_seed_data(db)
    clean_name = name.strip()
    clean_template = template.strip()
    if not clean_name:
        raise ValueError("技能名称不能为")
    if not clean_template:
        raise ValueError("执行模板不能为空")

    category = resolve_category(db, category_id=category_id, category_name=category_name)
    max_sort = max((skill.sort_order for skill in list_skills(db)), default=0)
    base_code = skill_code_from_name(clean_name)
    code = base_code
    suffix = 1
    while db.query(Skill).filter(Skill.code == code).one_or_none() is not None:
        suffix += 1
        code = f"{base_code}_{suffix}"

    skill = Skill(
        code=code,
        name=clean_name,
        description=description.strip() or None,
        category_id=category.id,
        template=clean_template,
        status="active",
        sort_order=max_sort + 1,
        is_builtin=False,
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def update_skill(
    db: Session,
    skill_id: int,
    name: str | None = None,
    template: str | None = None,
    category_id: int | None = None,
    category_name: str | None = None,
    description: str | None = None,
) -> Skill:
    ensure_seed_data(db)
    skill = db.query(Skill).filter(Skill.id == skill_id, Skill.status == "active").first()
    if not skill:
        raise ValueError("SKILL 不存")

    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("技能名称不能为")
        skill.name = clean_name
    if template is not None:
        clean_template = template.strip()
        if not clean_template:
            raise ValueError("执行模板不能为空")
        skill.template = clean_template
        skill.version += 1
    if description is not None:
        skill.description = description.strip() or None
    if category_id is not None or (category_name or "").strip():
        category = resolve_category(
            db,
            category_id=category_id,
            category_name=category_name or "",
        )
        skill.category_id = category.id

    db.commit()
    db.refresh(skill)
    return skill


def delete_skill(db: Session, skill_id: int) -> None:
    ensure_seed_data(db)
    skill = db.query(Skill).filter(Skill.id == skill_id, Skill.status == "active").first()
    if not skill:
        raise ValueError("SKILL 不存")
    skill.status = "deleted"
    db.commit()


def serialize_category(category: SkillCategory) -> dict:
    return {
        "id": category.id,
        "code": category.code,
        "name": category.name,
        "description": category.description or "",
        "sort_order": category.sort_order,
    }


def serialize_skill(skill: Skill) -> dict:
    return {
        "id": skill.id,
        "code": skill.code,
        "name": skill.name,
        "cat": skill.category.name,
        "category_id": skill.category_id,
        "desc": skill.description or "",
        "tpl": skill.template,
        "status": skill.status,
        "version": skill.version,
        "useCnt": skill.use_count,
    }


def get_default_category(db: Session) -> SkillCategory:
    """Return default skill category."""
    ensure_seed_data(db)
    default = db.query(SkillCategory).filter(
        SkillCategory.name == "活动分析",
        SkillCategory.is_enabled.is_(True)
    ).first()
    if not default:
        default = db.query(SkillCategory).filter(
            SkillCategory.is_enabled.is_(True)
        ).order_by(SkillCategory.sort_order).first()
    if not default:
        raise ValueError("默认分类不存")
    return default


def delete_category(db: Session, category_id: int) -> bool:
    """Delete a category and move skills to the default category."""
    ensure_seed_data(db)
    
    category = db.query(SkillCategory).filter(SkillCategory.id == category_id).first()
    if not category:
        raise ValueError("分类不存")
    
    # 获取默认分类（第一个分类）
    default_category = get_default_category(db)
    
    # Default category cannot be deleted.
    if category.id == default_category.id:
        raise ValueError("默认分类不可删除")
    
    # 将该分类下的所有技能迁移到默认分类
    skills_to_migrate = db.query(Skill).filter(Skill.category_id == category_id).all()
    for skill in skills_to_migrate:
        skill.category_id = default_category.id
    
    # 删除分类
    db.delete(category)
    db.commit()
    
    return True


def update_skill_category(db: Session, skill_id: int, new_category_id: int) -> Skill:
    """Update the category for a skill."""
    ensure_seed_data(db)
    
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise ValueError("技能不存在")
    
    new_category = db.query(SkillCategory).filter(
        SkillCategory.id == new_category_id,
        SkillCategory.is_enabled.is_(True)
    ).first()
    if not new_category:
        raise ValueError("目标分类不存")
    
    skill.category_id = new_category_id
    db.commit()
    db.refresh(skill)
    return skill


def record_skill_component_usage(
    skill_refs: list[Any],
    *,
    request_id: str = "",
    source_type: str = "",
    source_id: str | int = "",
    source_code: str = "",
    scene: str = "activity_analysis",
    framework_id: int | None = None,
    used_by: str = "",
    result_status: str = "success",
) -> int:
    """Record one usage for each resolved skill component.

    The source fields are generic on purpose: today the source is an activity
    template, while future free-form component composition can reuse the same
    log contract with a different source_type/source_id.
    """
    normalized_refs = _normalize_skill_refs(skill_refs)
    if not normalized_refs:
        return 0

    with SessionLocal() as db:
        ensure_seed_data(db)
        skills = _resolve_skills(db, normalized_refs)
        if not skills:
            logger.info(
                "skill usage skipped: request_id=%s reason=no_resolved_skills refs=%d",
                request_id or "-",
                len(normalized_refs),
            )
            return 0

        clean_scene = str(scene or "activity_analysis").strip() or "activity_analysis"
        clean_request_id = str(request_id or "").strip() or None
        clean_source_type = str(source_type or "").strip() or None
        clean_source_id = str(source_id or "").strip() or None
        clean_source_code = str(source_code or "").strip() or None
        clean_used_by = str(used_by or "").strip() or None
        clean_result_status = str(result_status or "success").strip() or "success"

        for skill in skills:
            skill.use_count += 1
            db.add(
                SkillUsageLog(
                    skill_id=skill.id,
                    framework_id=framework_id,
                    scene=clean_scene,
                    request_id=clean_request_id,
                    source_type=clean_source_type,
                    source_id=clean_source_id,
                    source_code=clean_source_code,
                    used_by=clean_used_by,
                    result_status=clean_result_status,
                )
            )
        db.commit()
        logger.info(
            "skill usage recorded: request_id=%s source_type=%s source_code=%s count=%d",
            clean_request_id or "-",
            clean_source_type or "-",
            clean_source_code or "-",
            len(skills),
        )
        return len(skills)


def _normalize_skill_refs(skill_refs: list[Any]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in skill_refs or []:
        if isinstance(ref, dict):
            item = {
                "id": str(ref.get("id") or ref.get("skill_id") or "").strip(),
                "code": str(ref.get("code") or ref.get("skill_code") or "").strip(),
                "name": str(ref.get("name") or ref.get("skill_name") or ref.get("title") or "").strip(),
            }
        else:
            item = {"id": "", "code": "", "name": str(ref or "").strip()}

        key = (item["id"], item["code"], item["name"])
        if key == ("", "", "") or key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def _resolve_skills(db: Session, skill_refs: list[dict[str, str]]) -> list[Skill]:
    resolved: list[Skill] = []
    seen_ids: set[int] = set()
    for ref in skill_refs:
        skill = None
        if ref["id"].isdigit():
            skill = db.query(Skill).filter(Skill.id == int(ref["id"]), Skill.status == "active").one_or_none()
        if skill is None and ref["code"]:
            skill = db.query(Skill).filter(Skill.code == ref["code"], Skill.status == "active").one_or_none()
        if skill is None and ref["name"]:
            skill = db.query(Skill).filter(Skill.name == ref["name"], Skill.status == "active").one_or_none()
        if skill is None or skill.id in seen_ids:
            continue
        seen_ids.add(skill.id)
        resolved.append(skill)
    return resolved
