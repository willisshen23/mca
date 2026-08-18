-- Persist organization and activity details used by the usage-detail export.
-- Each statement is idempotent on MySQL 8.0.

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
