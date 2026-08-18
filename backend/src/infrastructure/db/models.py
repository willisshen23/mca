from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for database models.

    The models intentionally use SQLAlchemy portable types so the same metadata
    can create tables on SQLite for local use and MySQL in production.
    """


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SkillCategory(Base, TimestampMixin):
    __tablename__ = "skill_categories"
    __table_args__ = (
        UniqueConstraint("code", name="uq_skill_categories_code"),
        Index("ix_skill_categories_parent_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("skill_categories.id", ondelete="SET NULL"),
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    parent: Mapped["SkillCategory | None"] = relationship(remote_side=[id])
    skills: Mapped[list["Skill"]] = relationship(back_populates="category")


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("code", name="uq_skills_code"),
        Index("ix_skills_category_id", "category_id"),
        Index("ix_skills_status", "status"),
        Index("ix_skills_is_builtin", "is_builtin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    category_id: Mapped[int] = mapped_column(
        ForeignKey("skill_categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    template: Mapped[str] = mapped_column(Text, nullable=False)
    config_schema: Mapped[str | None] = mapped_column(Text)
    input_schema: Mapped[str | None] = mapped_column(Text)
    output_schema: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))

    category: Mapped[SkillCategory] = relationship(back_populates="skills")
    versions: Mapped[list["SkillVersion"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )
    tag_links: Mapped[list["SkillTagLink"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class SkillVersion(Base, TimestampMixin):
    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint("skill_id", "version", name="uq_skill_versions_skill_version"),
        Index("ix_skill_versions_skill_id", "skill_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    config_schema: Mapped[str | None] = mapped_column(Text)
    change_note: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[str | None] = mapped_column(String(80))

    skill: Mapped[Skill] = relationship(back_populates="versions")


class SkillTag(Base, TimestampMixin):
    __tablename__ = "skill_tags"
    __table_args__ = (UniqueConstraint("name", name="uq_skill_tags_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str | None] = mapped_column(String(20))

    skill_links: Mapped[list["SkillTagLink"]] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
    )


class SkillTagLink(Base):
    __tablename__ = "skill_tag_links"
    __table_args__ = (
        UniqueConstraint("skill_id", "tag_id", name="uq_skill_tag_links_skill_tag"),
        Index("ix_skill_tag_links_tag_id", "tag_id"),
    )

    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("skill_tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    skill: Mapped[Skill] = relationship(back_populates="tag_links")
    tag: Mapped[SkillTag] = relationship(back_populates="skill_links")


class AnalysisFramework(Base, TimestampMixin):
    __tablename__ = "analysis_frameworks"
    __table_args__ = (
        Index("ix_analysis_frameworks_scene", "scene"),
        Index("ix_analysis_frameworks_is_default", "is_default"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    scene: Mapped[str] = mapped_column(String(30), nullable=False, default="online")
    description: Mapped[str | None] = mapped_column(String(500))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(80))

    skill_links: Mapped[list["FrameworkSkill"]] = relationship(
        back_populates="framework",
        cascade="all, delete-orphan",
        order_by="FrameworkSkill.position",
    )


class FrameworkSkill(Base):
    __tablename__ = "framework_skills"
    __table_args__ = (
        UniqueConstraint("framework_id", "position", name="uq_framework_skills_position"),
        Index("ix_framework_skills_skill_id", "skill_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    framework_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_frameworks.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    custom_title: Mapped[str | None] = mapped_column(String(120))
    custom_config: Mapped[str | None] = mapped_column(Text)

    framework: Mapped[AnalysisFramework] = relationship(back_populates="skill_links")
    skill: Mapped[Skill] = relationship()


class ActivityAnalysisTemplate(Base, TimestampMixin):
    __tablename__ = "activity_analysis_templates"
    __table_args__ = (
        UniqueConstraint("code", name="uq_activity_analysis_templates_code"),
        Index("ix_activity_analysis_templates_type", "type"),
        Index("ix_activity_analysis_templates_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False, default="通用")
    description: Mapped[str | None] = mapped_column(String(500))
    skills_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    icon: Mapped[str] = mapped_column(String(60), nullable=False, default="ti-layout-cards")
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#165DFF")
    bg: Mapped[str] = mapped_column(String(20), nullable=False, default="#E8F0FF")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class SystemPrompt(Base, TimestampMixin):
    __tablename__ = "SYSTEM_PROMPT"
    __table_args__ = (
        UniqueConstraint("prompt_key", name="uq_system_prompt_key"),
        Index("ix_system_prompt_agent_name", "agent_name"),
        Index("ix_system_prompt_status", "status"),
        Index("ix_system_prompt_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prompt_key: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_name: Mapped[str] = mapped_column(String(160), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    scenario: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    published_content: Mapped[str | None] = mapped_column(Text)
    variables_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(80))
    updated_by: Mapped[str | None] = mapped_column(String(80))


class QuickPrompt(Base, TimestampMixin):
    __tablename__ = "quick_prompts"
    __table_args__ = (
        Index("ix_quick_prompts_sort_order", "sort_order"),
        Index("ix_quick_prompts_is_enabled", "is_enabled"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UsageEvent(Base):
    """Small, append-only product usage event used by the management dashboard."""

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_event_created", "event_type", "created_at"),
        Index("ix_usage_events_user_created", "user_id", "created_at"),
        Index("ix_usage_events_org_created", "org_no", "created_at"),
        Index("ix_usage_events_session_id", "session_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    org_no: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str | None] = mapped_column(String(64))
    path: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str | None] = mapped_column(String(80))
    referrer: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class LlmTokenUsageLog(Base):
    """Append-only token and latency metrics for one LLM request."""

    __tablename__ = "llm_token_usage_logs"
    __table_args__ = (
        CheckConstraint("time_spent >= 0", name="ck_llm_token_usage_time_spent"),
        CheckConstraint("token_cost >= 0", name="ck_llm_token_usage_token_cost"),
        CheckConstraint(
            "exec_status IN ('SUCCESS', 'FAILED')",
            name="ck_llm_token_usage_exec_status",
        ),
        Index("ix_llm_token_usage_etl_agent", "etl_dt", "agent_id"),
        Index("ix_llm_token_usage_etl_status", "etl_dt", "exec_status"),
        {"comment": "大模型单次调用 Token 消耗统计"},
    )

    etl_dt: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        default=date.today,
        comment="请求日期",
    )
    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        comment="标识唯一性的 UUID",
    )
    agent_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="rtl-ActivityReport",
        server_default="rtl-ActivityReport",
        comment="场景 ID",
    )
    name: Mapped[str] = mapped_column(
        String(256),
        nullable=False,
        default="活动分析助手",
        server_default="活动分析助手",
        comment="场景名称",
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        comment="请求开始时间",
    )
    time_spent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="执行耗时（毫秒）",
    )
    token_cost: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="单次 Token 总消耗",
    )
    exec_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="执行成功标识：SUCCESS / FAILED（大写）",
    )


class SkillUsageLog(Base):
    __tablename__ = "skill_usage_logs"
    __table_args__ = (
        Index("ix_skill_usage_logs_skill_id", "skill_id"),
        Index("ix_skill_usage_logs_used_at", "used_at"),
        Index("ix_skill_usage_logs_scene", "scene"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    framework_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_frameworks.id", ondelete="SET NULL"),
    )
    scene: Mapped[str] = mapped_column(String(30), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    source_type: Mapped[str | None] = mapped_column(String(40))
    source_id: Mapped[str | None] = mapped_column(String(80))
    source_code: Mapped[str | None] = mapped_column(String(120))
    used_by: Mapped[str | None] = mapped_column(String(80))
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    result_status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")

    skill: Mapped[Skill] = relationship()
    framework: Mapped[AnalysisFramework | None] = relationship()


class ConversationMeta(Base, TimestampMixin):
    """Conversation metadata linked to user and agent thread."""

    __tablename__ = "conversation_meta"
    __table_args__ = (
        Index("ix_conversation_meta_user_id", "user_id"),
        Index("ix_conversation_meta_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    agent_version: Mapped[str | None] = mapped_column(String(16), nullable=True)


class AgentRunHistory(Base, TimestampMixin):
    """History for each report-generation agent request."""

    __tablename__ = "agent_run_history"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_agent_run_history_request_id"),
        Index("ix_agent_run_history_thread_id", "thread_id"),
        Index("ix_agent_run_history_user_id", "user_id"),
        Index("ix_agent_run_history_status", "status"),
        Index("ix_agent_run_history_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64))
    user_name: Mapped[str | None] = mapped_column(String(120))
    org_no: Mapped[str | None] = mapped_column(String(64))
    user_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    final_response: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql")
    )
    prompt_text: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql")
    )
    report_file_path: Mapped[str | None] = mapped_column(Text)
    report_file_name: Mapped[str | None] = mapped_column(String(255))
    report_asset_name: Mapped[str | None] = mapped_column(String(255))
    report_asset_media_type: Mapped[str | None] = mapped_column(String(120))
    report_asset_blob: Mapped[bytes | None] = mapped_column(
        LargeBinary().with_variant(LONGBLOB(), "mysql")
    )
    report_feedback: Mapped[str | None] = mapped_column(String(16))
    feedback_user_id: Mapped[str | None] = mapped_column(String(64))
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activity_template_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    matched_data_template_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activity_ids_json: Mapped[str | None] = mapped_column(Text)
    activity_names_json: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    latest_version_no: Mapped[int | None] = mapped_column(Integer)


class ReportVersion(Base):
    """Immutable snapshot of one report version (generate / modify)."""

    __tablename__ = "report_versions"
    __table_args__ = (
        UniqueConstraint("request_id", "version_no", name="uq_report_versions_request_version"),
        Index("ix_report_versions_request_id", "request_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        ForeignKey("agent_run_history.request_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    report_asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    report_asset_media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    report_asset_blob: Mapped[bytes] = mapped_column(
        LargeBinary().with_variant(LONGBLOB(), "mysql"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="generate")
    change_note: Mapped[str | None] = mapped_column(String(500))
    feedback: Mapped[str | None] = mapped_column(String(16))
    feedback_comment: Mapped[str | None] = mapped_column(Text)
    feedback_user_id: Mapped[str | None] = mapped_column(String(64))
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 应用侧 UTC default：与 ConversationTurn.started_at（_now()）保持同一时钟。
    # 仅依赖 server_default=func.now() 时，MySQL 落库的是服务器本地时间，
    # 与 started_at 的 UTC 墙钟相差一个时区偏移，_report_placements 跨时钟
    # 比较会把旧版本报告锚定到最新用户轮次（v1 卡片错排到修改对话之后）。
    # server_default 保留为裸 SQL 插入的兜底。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class ConversationTurn(Base, TimestampMixin):
    """Full conversation turn persisted for management search and detail view."""

    __tablename__ = "conversation_turn"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_conversation_turn_request_id"),
        Index("ix_conversation_turn_thread_id", "thread_id"),
        Index("ix_conversation_turn_user_id", "user_id"),
        Index("ix_conversation_turn_status", "status"),
        Index("ix_conversation_turn_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64))
    user_name: Mapped[str | None] = mapped_column(String(120))
    org_no: Mapped[str | None] = mapped_column(String(64))
    user_text: Mapped[str | None] = mapped_column(Text)
    assistant_response: Mapped[str | None] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    has_report: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    channel: Mapped[str | None] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
