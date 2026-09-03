"""Lightweight schema maintenance helpers.

The project does not use Alembic.  On startup we only create missing tables.
When a new column is added to an existing table we must add it explicitly
through ALTER TABLE so existing deployments (SQLite local, MySQL prod) keep
working after a pull.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import Engine, inspect, text
from sqlalchemy.orm import Session

from src.infrastructure.db.models import (
    AgentRunHistory,
    ConversationMeta,
    ConversationTurn,
)

logger = logging.getLogger("activity-analysis.migrations")


def ensure_request_id_fk_compatible(engine: Engine) -> None:
    """Align agent_run_history.request_id with the ORM definition.

    report_versions.request_id references agent_run_history.request_id.
    Older MySQL deployments created agent_run_history with a divergent
    request_id column (length/charset/collation), so MySQL rejects the
    foreign key with error 3780 when report_versions is created.  Align the
    existing column before the create-table loop runs.  No-op on SQLite and
    on deployments where the column already matches.
    """
    if engine.dialect.name != "mysql":
        return
    inspector = inspect(engine)
    table_names = {name.casefold() for name in inspector.get_table_names()}
    if "agent_run_history" not in table_names or "report_versions" in table_names:
        return

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'agent_run_history'
                  AND COLUMN_NAME = 'request_id'
                """
            )
        ).fetchone()
        if row is None:
            return
        column_type, charset, collation = row
        db_charset, db_collation = conn.execute(
            text("SELECT @@character_set_database, @@collation_database")
        ).fetchone()

        if (
            column_type.lower() == "varchar(64)"
            and charset == db_charset
            and collation == db_collation
        ):
            return

        # Refuse to alter onto data that would not fit the target type or
        # would collide under the target collation; leave it for manual fix.
        max_len = conn.execute(
            text("SELECT MAX(LENGTH(request_id)) FROM agent_run_history")
        ).scalar()
        if max_len is not None and max_len > 64:
            logger.error(
                "agent_run_history.request_id holds values up to %d chars; "
                "refusing to shrink to VARCHAR(64), fix manually",
                max_len,
            )
            return
        collisions = conn.execute(
            text(
                f"""
                SELECT COUNT(*) FROM (
                    SELECT 1 FROM agent_run_history
                    GROUP BY CONVERT(request_id USING {db_charset}) COLLATE {db_collation}
                    HAVING COUNT(*) > 1
                ) dup
                """
            )
        ).scalar()
        if collisions:
            logger.error(
                "agent_run_history.request_id has duplicates under collation "
                "%s; refusing to alter, fix manually",
                db_collation,
            )
            return

        logger.info(
            "Aligning agent_run_history.request_id: %s %s/%s -> VARCHAR(64) %s/%s",
            column_type,
            charset,
            collation,
            db_charset,
            db_collation,
        )
        conn.execute(
            text(
                f"ALTER TABLE agent_run_history MODIFY request_id VARCHAR(64) "
                f"CHARACTER SET {db_charset} COLLATE {db_collation} NOT NULL"
            )
        )
        logger.info(
            "agent_run_history.request_id aligned; report_versions FK can be created"
        )


def ensure_conversation_turn_schema(engine: Engine) -> None:
    """Upgrade large-content conversation_turn columns to LONGTEXT on MySQL.

    Older MySQL deployments created assistant_response as TEXT (64 KiB cap),
    which report-sized responses exceed.  No-op on SQLite and on deployments
    already using LONGTEXT.
    """
    inspector = inspect(engine)
    table_names = {name.casefold() for name in inspector.get_table_names()}
    if "conversation_turn" not in table_names:
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("conversation_turn")
    }
    if "org_no" not in existing_columns:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE conversation_turn ADD COLUMN org_no VARCHAR(64) NULL"
            )
        logger.info("conversation_turn schema upgraded: added org_no")

    if engine.dialect.name != "mysql":
        return
    inspector = inspect(engine)
    column_types = {
        column["name"]: str(column.get("type") or "").upper()
        for column in inspector.get_columns("conversation_turn")
    }
    with engine.begin() as conn:
        for column_name in ("assistant_response",):
            if column_name in column_types and "LONGTEXT" not in column_types[column_name]:
                conn.execute(
                    text(
                        f"ALTER TABLE conversation_turn "
                        f"MODIFY COLUMN {column_name} LONGTEXT NULL"
                    )
                )
                logger.info(
                    "conversation_turn schema upgraded: %s %s -> LONGTEXT",
                    column_name,
                    column_types[column_name] or "unknown",
                )


def ensure_agent_version_column(engine: Engine) -> None:
    """Add agent_version to conversation_meta if it is missing."""
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("conversation_meta")}
    if "agent_version" in columns:
        return

    # SQLite and MySQL both support ADD COLUMN with a nullable column.
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "ALTER TABLE conversation_meta ADD COLUMN agent_version VARCHAR(16)"
        )
        conn.commit()


def ensure_usage_event_schema(engine: Engine) -> None:
    """Add organization tracking to usage_events on existing SQLite/MySQL databases."""
    inspector = inspect(engine)
    table_names = {name.casefold() for name in inspector.get_table_names()}
    if "usage_events" not in table_names:
        return

    columns = {column["name"].casefold() for column in inspector.get_columns("usage_events")}
    if "org_no" not in columns:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "ALTER TABLE usage_events ADD COLUMN org_no VARCHAR(64) NULL"
            )
        logger.info("usage_events schema upgraded: added org_no")

    # Refresh reflected indexes after a possible ALTER TABLE.
    inspector = inspect(engine)
    indexes = {
        str(index.get("name") or "").casefold()
        for index in inspector.get_indexes("usage_events")
    }
    if "ix_usage_events_org_created" not in indexes:
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE INDEX ix_usage_events_org_created "
                "ON usage_events (org_no, created_at)"
            )
        logger.info("usage_events schema upgraded: added organization/date index")


def _ensure_schema_migrations_table(engine: Engine) -> None:
    inspector = inspect(engine)
    if "schema_migrations" in inspector.get_table_names():
        return
    with engine.connect() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE schema_migrations (
                migration_name VARCHAR(128) PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _is_migration_applied(engine: Engine, name: str) -> bool:
    _ensure_schema_migrations_table(engine)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM schema_migrations WHERE migration_name = :name"),
            {"name": name},
        )
        return result.fetchone() is not None


def _mark_migration_applied(engine: Engine, name: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO schema_migrations (migration_name) VALUES (:name)"),
            {"name": name},
        )


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


async def cleanup_v1_data(engine: Engine) -> None:
    """Export and delete v1 conversation data plus associated checkpoints."""
    from pathlib import Path

    from src.config import get_settings, resolve_path

    migration_name = "cleanup_v1_data_2026_07_20"
    if _is_migration_applied(engine, migration_name):
        logger.info("cleanup_v1_data already applied, skipping")
        return

    ensure_agent_version_column(engine)

    with Session(engine) as session:
        v1_rows = session.query(ConversationMeta.thread_id).filter(
            (ConversationMeta.agent_version == "v1") | (ConversationMeta.agent_version.is_(None))
        ).all()
        v1_threads = [row[0] for row in v1_rows]

        if not v1_threads:
            _mark_migration_applied(engine, migration_name)
            return

        backup_dir = resolve_path("data/backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"v1_cleanup_{timestamp}.json"

        conversations = session.query(ConversationMeta).filter(
            ConversationMeta.thread_id.in_(v1_threads)
        ).all()
        histories = session.query(AgentRunHistory).filter(
            AgentRunHistory.thread_id.in_(v1_threads)
        ).all()
        turns = session.query(ConversationTurn).filter(
            ConversationTurn.thread_id.in_(v1_threads)
        ).all()

        def _clean(rows: list[object]) -> list[dict]:
            return [
                {k: v for k, v in row.__dict__.items() if not k.startswith("_")}
                for row in rows
            ]

        backup = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "thread_ids": v1_threads,
            "conversations": _clean(conversations),
            "agent_run_history": _clean(histories),
            "conversation_turns": _clean(turns),
        }
        backup_path.write_text(
            json.dumps(backup, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        logger.info(
            "Backed up %d v1 conversations to %s",
            len(v1_threads),
            backup_path,
        )

        session.query(AgentRunHistory).filter(
            AgentRunHistory.thread_id.in_(v1_threads)
        ).delete(synchronize_session=False)
        session.query(ConversationTurn).filter(
            ConversationTurn.thread_id.in_(v1_threads)
        ).delete(synchronize_session=False)
        session.query(ConversationMeta).filter(
            ConversationMeta.thread_id.in_(v1_threads)
        ).delete(synchronize_session=False)
        session.commit()

    # Delete checkpoints from the SQLite checkpoint database.
    settings = get_settings()
    db_path = resolve_path(settings.db_path)
    if db_path.exists() and v1_threads:
        import aiosqlite

        async def _delete_checkpoints() -> None:
            connection = await aiosqlite.connect(str(db_path))
            try:
                for thread_id in v1_threads:
                    try:
                        # v1 checkpoint 库表结构：checkpoints/writes，均按 thread_id 键控；
                        # 表可能不存在（老库），逐线程 try/except 告警即可
                        await connection.execute(
                            "DELETE FROM checkpoints WHERE thread_id = ?",
                            (thread_id,),
                        )
                        await connection.execute(
                            "DELETE FROM writes WHERE thread_id = ?",
                            (thread_id,),
                        )
                        await connection.commit()
                    except Exception as exc:
                        logger.warning(
                            "Failed to delete checkpoint for thread %s: %s",
                            thread_id,
                            exc,
                        )
            finally:
                await connection.close()

        await _delete_checkpoints()

    _mark_migration_applied(engine, migration_name)
    logger.info("cleanup_v1_data completed: removed %d v1 conversations", len(v1_threads))
