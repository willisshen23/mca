-- Store token consumption and latency for each LLM request.
-- Safe to run repeatedly on MySQL 8.0+; existing business data is untouched.
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
