from __future__ import annotations

import re
from pathlib import Path

from src.infrastructure.db.models import Base


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FULL_SCHEMA_PATH = PROJECT_ROOT / "data" / "mysql" / "schema.sql"
AUTO_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "mysql" / "auto_migrations"
MIGRATE_SCRIPT = PROJECT_ROOT / "backend" / "scripts" / "migrate-db.sh"
PYMYSQL_MIGRATOR = PROJECT_ROOT / "backend" / "scripts" / "migrate_db.py"


def test_full_schema_covers_every_orm_table():
    sql = FULL_SCHEMA_PATH.read_text(encoding="utf-8")
    sql_tables = {
        match.casefold()
        for match in re.findall(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([A-Za-z0-9_]+)`?",
            sql,
            flags=re.IGNORECASE,
        )
    }
    orm_tables = {table.name.casefold() for table in Base.metadata.sorted_tables}

    assert orm_tables <= sql_tables
    assert "schema_migrations" in sql_tables


def test_auto_migrations_are_versioned_and_mysql_compatible():
    migration_files = sorted(AUTO_MIGRATIONS_DIR.glob("*.sql"))

    assert migration_files
    assert [path.name for path in migration_files] == sorted(
        path.name for path in migration_files
    )
    for path in migration_files:
        script = path.read_text(encoding="utf-8")
        assert path.name[0:8].isdigit()
        assert "DEFAULT CURRENT_DATE" not in script
        assert "DEFAULT (CURRENT_DATE)" not in script


def test_database_deployment_uses_pymysql_without_mysql_cli():
    script = MIGRATE_SCRIPT.read_text(encoding="utf-8")
    python_migrator = PYMYSQL_MIGRATOR.read_text(encoding="utf-8")

    assert "auto|full|upgrade" in script
    assert 'migrate_db.py' in script
    assert 'PyMySQL' in script
    assert 'command -v mysql' not in script
    assert 'MYSQL_BASE' not in script

    assert 'CLIENT.MULTI_STATEMENTS' in python_migrator
    assert 'auto", "full", "upgrade"' in python_migrator
    assert 'schema_migrations' in python_migrator
    assert 'information_schema.SCHEMATA' in python_migrator


def test_official_start_scripts_run_database_deployment_before_uvicorn():
    for relative_path in (
        "backend/scripts/start.sh",
        "backend/scripts/start-offline.sh",
        "backend/scripts/server.sh",
    ):
        script = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        migration_position = script.find("migrate-db.sh")
        uvicorn_position = script.find("python -m uvicorn")

        assert migration_position >= 0, relative_path
        assert uvicorn_position > migration_position, relative_path
