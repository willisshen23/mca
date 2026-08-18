-- Usage dashboard event storage.
-- Safe to run repeatedly on MySQL 5.7+/8.0; existing business data is untouched.
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
