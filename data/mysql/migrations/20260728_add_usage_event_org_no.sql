-- Add institution-number tracking to an existing usage_events table.
-- Idempotent on MySQL 8.0 and safe for controlled repeated deployments.
SET @org_column_sql = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'usage_events'
          AND COLUMN_NAME = 'org_no'
    ),
    'SELECT 1',
    'ALTER TABLE usage_events ADD COLUMN org_no VARCHAR(64) NULL AFTER user_id'
);
PREPARE org_column_stmt FROM @org_column_sql;
EXECUTE org_column_stmt;
DEALLOCATE PREPARE org_column_stmt;

SET @org_index_sql = IF(
    EXISTS(
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'usage_events'
          AND INDEX_NAME = 'ix_usage_events_org_created'
    ),
    'SELECT 1',
    'CREATE INDEX ix_usage_events_org_created ON usage_events (org_no, created_at)'
);
PREPARE org_index_stmt FROM @org_index_sql;
EXECUTE org_index_stmt;
DEALLOCATE PREPARE org_index_stmt;
