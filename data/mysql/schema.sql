-- MySQL 8.0+ business database schema for njbank Marketing Campaign Analysis.
-- Select the target database before running this script. The script does not
-- create or drop a database and can be run repeatedly.
-- 创建库名
-- CREATE DATABASE njbank_aa
-- CHARACTER SET utf8mb4
-- COLLATE utf8mb4_unicode_ci;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS skill_categories (
    id INTEGER NOT NULL AUTO_INCREMENT,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) NULL,
    parent_id INTEGER NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_skill_categories_code UNIQUE (code),
    CONSTRAINT fk_skill_categories_parent_id
        FOREIGN KEY (parent_id) REFERENCES skill_categories (id) ON DELETE SET NULL,
    INDEX ix_skill_categories_parent_id (parent_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER NOT NULL AUTO_INCREMENT,
    code VARCHAR(80) NOT NULL,
    name VARCHAR(120) NOT NULL,
    description VARCHAR(500) NULL,
    category_id INTEGER NOT NULL,
    template TEXT NOT NULL,
    config_schema TEXT NULL,
    input_schema TEXT NULL,
    output_schema TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    version INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    use_count INTEGER NOT NULL DEFAULT 0,
    is_builtin TINYINT(1) NOT NULL DEFAULT 0,
    created_by VARCHAR(80) NULL,
    updated_by VARCHAR(80) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_skills_code UNIQUE (code),
    CONSTRAINT fk_skills_category_id
        FOREIGN KEY (category_id) REFERENCES skill_categories (id) ON DELETE RESTRICT,
    INDEX ix_skills_category_id (category_id),
    INDEX ix_skills_status (status),
    INDEX ix_skills_is_builtin (is_builtin)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS skill_versions (
    id INTEGER NOT NULL AUTO_INCREMENT,
    skill_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    template TEXT NOT NULL,
    config_schema TEXT NULL,
    change_note VARCHAR(500) NULL,
    created_by VARCHAR(80) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_skill_versions_skill_version UNIQUE (skill_id, version),
    CONSTRAINT fk_skill_versions_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE,
    INDEX ix_skill_versions_skill_id (skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS skill_tags (
    id INTEGER NOT NULL AUTO_INCREMENT,
    name VARCHAR(80) NOT NULL,
    color VARCHAR(20) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_skill_tags_name UNIQUE (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS skill_tag_links (
    skill_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (skill_id, tag_id),
    CONSTRAINT fk_skill_tag_links_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE CASCADE,
    CONSTRAINT fk_skill_tag_links_tag_id
        FOREIGN KEY (tag_id) REFERENCES skill_tags (id) ON DELETE CASCADE,
    INDEX ix_skill_tag_links_tag_id (tag_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS analysis_frameworks (
    id INTEGER NOT NULL AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    scene VARCHAR(30) NOT NULL DEFAULT 'online',
    description VARCHAR(500) NULL,
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    is_enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_by VARCHAR(80) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX ix_analysis_frameworks_scene (scene),
    INDEX ix_analysis_frameworks_is_default (is_default)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS framework_skills (
    id INTEGER NOT NULL AUTO_INCREMENT,
    framework_id INTEGER NOT NULL,
    skill_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    custom_title VARCHAR(120) NULL,
    custom_config TEXT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_framework_skills_position UNIQUE (framework_id, position),
    CONSTRAINT fk_framework_skills_framework_id
        FOREIGN KEY (framework_id) REFERENCES analysis_frameworks (id) ON DELETE CASCADE,
    CONSTRAINT fk_framework_skills_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE RESTRICT,
    INDEX ix_framework_skills_skill_id (skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS activity_analysis_templates (
    id INTEGER NOT NULL AUTO_INCREMENT,
    code VARCHAR(80) NOT NULL,
    name VARCHAR(120) NOT NULL,
    type VARCHAR(40) NOT NULL DEFAULT '通用',
    description VARCHAR(500) NULL,
    skills_json TEXT NOT NULL,
    icon VARCHAR(60) NOT NULL DEFAULT 'ti-layout-cards',
    color VARCHAR(20) NOT NULL DEFAULT '#165DFF',
    bg VARCHAR(20) NOT NULL DEFAULT '#E8F0FF',
    use_count INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    is_builtin TINYINT(1) NOT NULL DEFAULT 0,
    created_by VARCHAR(80) NULL,
    updated_by VARCHAR(80) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_activity_analysis_templates_code UNIQUE (code),
    INDEX ix_activity_analysis_templates_type (type),
    INDEX ix_activity_analysis_templates_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `SYSTEM_PROMPT` (
    id INTEGER NOT NULL AUTO_INCREMENT,
    prompt_key VARCHAR(120) NOT NULL,
    prompt_name VARCHAR(160) NOT NULL,
    agent_name VARCHAR(80) NOT NULL,
    scenario VARCHAR(80) NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    published_content TEXT NULL,
    variables_json TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    is_active TINYINT(1) NOT NULL DEFAULT 0,
    created_by VARCHAR(80) NULL,
    updated_by VARCHAR(80) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_system_prompt_key UNIQUE (prompt_key),
    INDEX ix_system_prompt_agent_name (agent_name),
    INDEX ix_system_prompt_status (status),
    INDEX ix_system_prompt_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quick_prompts (
    id INTEGER NOT NULL AUTO_INCREMENT,
    text VARCHAR(500) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_enabled TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX ix_quick_prompts_sort_order (sort_order),
    INDEX ix_quick_prompts_is_enabled (is_enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(40) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    org_no VARCHAR(64) NULL,
    session_id VARCHAR(64) NULL,
    path VARCHAR(255) NULL,
    source VARCHAR(80) NULL,
    referrer VARCHAR(500) NULL,
    metadata_json TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX ix_usage_events_event_created (event_type, created_at),
    INDEX ix_usage_events_user_created (user_id, created_at),
    INDEX ix_usage_events_org_created (org_no, created_at),
    INDEX ix_usage_events_session_id (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS llm_token_usage_logs (
    etl_dt DATE NOT NULL COMMENT '请求日期',
    id VARCHAR(64) NOT NULL COMMENT '标识唯一性的 UUID',
    agent_id VARCHAR(128) NOT NULL DEFAULT 'rtl-ActivityReport' COMMENT '场景 ID',
    name VARCHAR(256) NOT NULL DEFAULT '活动分析助手' COMMENT '场景名称',
    start_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '请求开始时间',
    time_spent INT NOT NULL COMMENT '执行耗时（毫秒）',
    token_cost INT NOT NULL COMMENT '单次 Token 总消耗',
    exec_status VARCHAR(32) NOT NULL COMMENT '执行成功标识：SUCCESS / FAILED（大写）',
    PRIMARY KEY (id),
    CONSTRAINT ck_llm_token_usage_time_spent CHECK (time_spent >= 0),
    CONSTRAINT ck_llm_token_usage_token_cost CHECK (token_cost >= 0),
    CONSTRAINT ck_llm_token_usage_exec_status
        CHECK (exec_status IN ('SUCCESS', 'FAILED')),
    INDEX ix_llm_token_usage_etl_agent (etl_dt, agent_id),
    INDEX ix_llm_token_usage_etl_status (etl_dt, exec_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='大模型单次调用 Token 消耗统计';

CREATE TABLE IF NOT EXISTS skill_usage_logs (
    id INTEGER NOT NULL AUTO_INCREMENT,
    skill_id INTEGER NOT NULL,
    framework_id INTEGER NULL,
    scene VARCHAR(30) NOT NULL,
    request_id VARCHAR(64) NULL,
    source_type VARCHAR(40) NULL,
    source_id VARCHAR(80) NULL,
    source_code VARCHAR(120) NULL,
    used_by VARCHAR(80) NULL,
    used_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER NULL,
    result_status VARCHAR(20) NOT NULL DEFAULT 'success',
    PRIMARY KEY (id),
    CONSTRAINT fk_skill_usage_logs_skill_id
        FOREIGN KEY (skill_id) REFERENCES skills (id) ON DELETE RESTRICT,
    CONSTRAINT fk_skill_usage_logs_framework_id
        FOREIGN KEY (framework_id) REFERENCES analysis_frameworks (id) ON DELETE SET NULL,
    INDEX ix_skill_usage_logs_skill_id (skill_id),
    INDEX ix_skill_usage_logs_used_at (used_at),
    INDEX ix_skill_usage_logs_scene (scene)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS conversation_meta (
    id INTEGER NOT NULL AUTO_INCREMENT,
    thread_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NULL,
    agent_version VARCHAR(16) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_conversation_meta_thread_id UNIQUE (thread_id),
    INDEX ix_conversation_meta_user_id (user_id),
    INDEX ix_conversation_meta_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_run_history (
    id INTEGER NOT NULL AUTO_INCREMENT,
    request_id VARCHAR(64) NOT NULL,
    thread_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NULL,
    user_name VARCHAR(120) NULL,
    org_no VARCHAR(64) NULL,
    user_text TEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    failure_reason TEXT NULL,
    final_response LONGTEXT NULL,
    prompt_text LONGTEXT NULL,
    report_file_path TEXT NULL,
    report_file_name VARCHAR(255) NULL,
    report_asset_name VARCHAR(255) NULL,
    report_asset_media_type VARCHAR(120) NULL,
    report_asset_blob LONGBLOB NULL,
    report_feedback VARCHAR(16) NULL,
    feedback_user_id VARCHAR(64) NULL,
    feedback_at DATETIME NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    activity_template_snapshot JSON NULL,
    matched_data_template_name VARCHAR(255) NULL,
    activity_ids_json TEXT NULL,
    activity_names_json TEXT NULL,
    duration_ms INTEGER NULL,
    latest_version_no INTEGER NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_agent_run_history_request_id UNIQUE (request_id),
    INDEX ix_agent_run_history_thread_id (thread_id),
    INDEX ix_agent_run_history_user_id (user_id),
    INDEX ix_agent_run_history_status (status),
    INDEX ix_agent_run_history_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS report_versions (
    id INTEGER NOT NULL AUTO_INCREMENT,
    request_id VARCHAR(64) NOT NULL,
    version_no INTEGER NOT NULL,
    report_asset_name VARCHAR(255) NOT NULL,
    report_asset_media_type VARCHAR(120) NOT NULL,
    report_asset_blob LONGBLOB NOT NULL,
    source VARCHAR(20) NOT NULL DEFAULT 'generate',
    change_note VARCHAR(500) NULL,
    feedback VARCHAR(16) NULL,
    feedback_comment TEXT NULL,
    feedback_user_id VARCHAR(64) NULL,
    feedback_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_report_versions_request_version UNIQUE (request_id, version_no),
    CONSTRAINT fk_report_versions_request_id
        FOREIGN KEY (request_id) REFERENCES agent_run_history (request_id) ON DELETE CASCADE,
    INDEX ix_report_versions_request_id (request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS conversation_turn (
    id INTEGER NOT NULL AUTO_INCREMENT,
    request_id VARCHAR(64) NOT NULL,
    thread_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NULL,
    user_name VARCHAR(120) NULL,
    org_no VARCHAR(64) NULL,
    user_text TEXT NULL,
    assistant_response LONGTEXT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    failure_reason TEXT NULL,
    has_report TINYINT(1) NOT NULL DEFAULT 0,
    channel VARCHAR(40) NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    duration_ms INTEGER NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT uq_conversation_turn_request_id UNIQUE (request_id),
    INDEX ix_conversation_turn_thread_id (thread_id),
    INDEX ix_conversation_turn_user_id (user_id),
    INDEX ix_conversation_turn_status (status),
    INDEX ix_conversation_turn_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name VARCHAR(128) NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (migration_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
