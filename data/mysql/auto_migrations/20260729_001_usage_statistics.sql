-- dialects: mysql
-- 首页运营统计、使用明细导出及大模型 Token 统计升级。
-- 脚本必须保持幂等，以便发生中断后安全重试。

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

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'usage_events'
          AND COLUMN_NAME = 'org_no'
    ),
    'SELECT 1',
    'ALTER TABLE usage_events ADD COLUMN org_no VARCHAR(64) NULL AFTER user_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'usage_events'
          AND INDEX_NAME = 'ix_usage_events_org_created'
    ),
    'SELECT 1',
    'CREATE INDEX ix_usage_events_org_created ON usage_events (org_no, created_at)'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'agent_run_history'
          AND COLUMN_NAME = 'org_no'
    ),
    'SELECT 1',
    'ALTER TABLE agent_run_history ADD COLUMN org_no VARCHAR(64) NULL AFTER user_name'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'agent_run_history'
          AND COLUMN_NAME = 'activity_ids_json'
    ),
    'SELECT 1',
    'ALTER TABLE agent_run_history ADD COLUMN activity_ids_json TEXT NULL AFTER matched_data_template_name'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'agent_run_history'
          AND COLUMN_NAME = 'activity_names_json'
    ),
    'SELECT 1',
    'ALTER TABLE agent_run_history ADD COLUMN activity_names_json TEXT NULL AFTER activity_ids_json'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'conversation_turn'
          AND COLUMN_NAME = 'org_no'
    ),
    'SELECT 1',
    'ALTER TABLE conversation_turn ADD COLUMN org_no VARCHAR(64) NULL AFTER user_name'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

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
