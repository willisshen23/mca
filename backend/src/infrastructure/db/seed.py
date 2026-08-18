from __future__ import annotations

from sqlalchemy.orm import Session

from src.infrastructure.db.models import AnalysisFramework, FrameworkSkill, Skill, SkillCategory, SkillVersion


DEFAULT_SKILLS = [
    {"code": "activity_participation", "name": "活动参与率分", "cat": "活动分析", "desc": "统计参与人数及漏", "tpl": "1. 参与率计算\n2. 分层分析"},
    {"code": "customer_behavior_tags", "name": "客群行为标签分析", "cat": "客群分析", "desc": "识别高价值客", "tpl": "1. 标签提取\n2. 聚类分析"},
    {"code": "channel_effect_compare", "name": "渠道效果对比", "cat": "渠道分析", "desc": "多渠ROI 对比", "tpl": "1. 渠道汇总\n2. ROI 计算"},
    {"code": "activity_roi", "name": "活动ROI分析", "cat": "财务分析", "desc": "成本收益分析", "tpl": "1. 成本统计\n2. 净 ROI"},
    {"code": "conversion_path", "name": "转化路径分析", "cat": "活动分析", "desc": "全链路分", "tpl": "1. 路径梳理\n2. 流失节点"},
    {"code": "risk_customer_detect", "name": "风险客群识别", "cat": "风控分析", "desc": "异常行为检", "tpl": "1. 规则检测\n2. 风险评分"},
    {"code": "product_preference", "name": "产品偏好分析", "cat": "客群分析", "desc": "偏好建模", "tpl": "1. 偏好提取\n2. 推荐策略"},
    {"code": "time_series_trend", "name": "时间序列趋势", "cat": "通用分析", "desc": "时序趋势识别", "tpl": "1. 数据处理\n2. 趋势识别"},
]


def seed_default_skills(db: Session) -> None:
    categories: dict[str, SkillCategory] = {}
    for sort_order, name in enumerate(["默认分类", "客群分析", "渠道分析", "财务分析", "风控分析", "通用分析"], start=1):
        code = f"cat_{sort_order}"
        category = db.query(SkillCategory).filter(SkillCategory.name == name).one_or_none()
        if category is None:
            category = SkillCategory(code=code, name=name, sort_order=sort_order, is_enabled=True)
            db.add(category)
            db.flush()
        categories[name] = category

    skills: list[Skill] = []
    for sort_order, item in enumerate(DEFAULT_SKILLS, start=1):
        skill = db.query(Skill).filter(Skill.code == item["code"]).one_or_none()
        if skill is None:
            cat_name = item["cat"]
            # 如果原始分类活动分析，改默认分类"
            if cat_name == "活动分析":
                cat_name = "默认分类"
            skill = Skill(
                code=item["code"],
                name=item["name"],
                description=item["desc"],
                category_id=categories[cat_name].id,
                template=item["tpl"],
                status="active",
                sort_order=sort_order,
                is_builtin=True,
            )
            db.add(skill)
            db.flush()
            db.add(
                SkillVersion(
                    skill_id=skill.id,
                    version=1,
                    template=item["tpl"],
                    change_note="初始化默SKILL",
                    created_by="system",
                )
            )
        skills.append(skill)

    default_framework = (
        db.query(AnalysisFramework)
        .filter(AnalysisFramework.name == "默认活动分析框架")
        .one_or_none()
    )
    if default_framework is None:
        default_framework = AnalysisFramework(
            name="默认活动分析框架",
            scene="online",
            description="默认包含活动、客群、渠道、ROI 与转化路径分析",
            is_default=True,
            is_enabled=True,
            created_by="system",
        )
        db.add(default_framework)
        db.flush()
        for position, skill in enumerate(skills[:5], start=1):
            db.add(
                FrameworkSkill(
                    framework_id=default_framework.id,
                    skill_id=skill.id,
                    position=position,
                )
            )

    db.commit()
