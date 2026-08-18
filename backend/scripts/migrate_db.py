#!/usr/bin/env python3
"""使用 PyMySQL 部署 MySQL 协议兼容数据库。

该迁移器是 migrate-db.sh 在目标机没有 mysql 命令时的离线后备路径。
它与 Shell 入口共享 auto/full/upgrade 三种模式，并使用同一套 SQL 文件。
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
from typing import Any

try:
    import pymysql
    from pymysql.constants import CLIENT
except ImportError as exc:  # pragma: no cover - 仅用于目标机错误提示
    raise SystemExit(
        "[database] 错误: 当前 Python 环境未安装 PyMySQL，无法执行数据库部署"
    ) from exc

try:
    from dotenv import dotenv_values
except ImportError as exc:  # pragma: no cover - 仅用于目标机错误提示
    raise SystemExit(
        "[database] 错误: 当前 Python 环境未安装 python-dotenv，无法读取数据库配置"
    ) from exc


SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
ENV_FILE = Path(os.environ.get("ENV_FILE", BACKEND_DIR / ".env"))
FULL_SCHEMA = PROJECT_ROOT / "data" / "mysql" / "schema.sql"
MIGRATIONS_DIR = PROJECT_ROOT / "data" / "mysql" / "auto_migrations"


def log(message: str) -> None:
    print(f"[database] {message}", flush=True)


def die(message: str) -> None:
    raise SystemExit(f"[database] 错误: {message}")


def load_config() -> dict[str, str]:
    file_values: dict[str, Any] = {}
    if ENV_FILE.is_file():
        file_values = dict(dotenv_values(ENV_FILE))

    def value(name: str) -> str:
        current = os.environ.get(name)
        if current is None:
            current = file_values.get(name)
        return str(current or "").strip()

    config = {
        "host": value("DATABASE_HOST"),
        "port": value("DATABASE_PORT"),
        "user": value("DATABASE_USERNAME"),
        "password": value("DATABASE_PASSWORD"),
        "database": value("DATABASE_NAME"),
    }
    if not config["host"]:
        log("未配置 DATABASE_HOST，当前为 SQLite 模式，跳过 MySQL SQL 部署")
        raise SystemExit(0)

    missing = [
        env_name
        for env_name, key in (
            ("DATABASE_PORT", "port"),
            ("DATABASE_USERNAME", "user"),
            ("DATABASE_NAME", "database"),
        )
        if not config[key]
    ]
    if missing:
        die("缺少 " + "、".join(missing))
    if not config["port"].isdigit() or not 1 <= int(config["port"]) <= 65535:
        die("DATABASE_PORT 必须是 1 到 65535 之间的数字")
    if not re.fullmatch(r"[A-Za-z0-9_]+", config["database"]):
        die("DATABASE_NAME 只能包含字母、数字和下划线")
    return config


def connect(config: dict[str, str], database: str | None = None):
    return pymysql.connect(
        host=config["host"],
        port=int(config["port"]),
        user=config["user"],
        password=config["password"],
        database=database,
        charset="utf8mb4",
        autocommit=True,
        client_flag=CLIENT.MULTI_STATEMENTS,
        connect_timeout=10,
        read_timeout=120,
        write_timeout=120,
    )


def scalar(connection, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        row = cursor.fetchone()
    return row[0] if row else None


def execute_script(connection, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            while cursor.nextset():
                pass
    except Exception as exc:
        die(f"执行 SQL 失败（{path.name}）: {exc}")


def database_exists(connection, database: str) -> bool:
    result = scalar(
        connection,
        "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s",
        (database,),
    )
    return int(result or 0) == 1


def schema_initialized(connection, database: str) -> bool:
    result = scalar(
        connection,
        """
        SELECT COUNT(*)
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='skill_categories'
        """,
        (database,),
    )
    return int(result or 0) == 1


def create_database(connection, database: str) -> None:
    log(f"创建或确认数据库: {database}")
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{database}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )


def ensure_migration_table(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name VARCHAR(128) NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (migration_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )


def run_incremental_migrations(connection) -> None:
    ensure_migration_table(connection)
    for migration_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        migration_name = f"sql:{migration_file.name}"
        applied = scalar(
            connection,
            "SELECT COUNT(*) FROM schema_migrations WHERE migration_name=%s",
            (migration_name,),
        )
        if int(applied or 0) == 1:
            log(f"跳过已执行版本: {migration_file.name}")
            continue
        log(f"执行增量 SQL: {migration_file.name}")
        execute_script(connection, migration_file)
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO schema_migrations (migration_name) VALUES (%s)",
                (migration_name,),
            )
        log(f"增量 SQL 执行成功: {migration_file.name}")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if mode not in {"auto", "full", "upgrade"}:
        die(f"不支持的模式: {mode}（可选 auto、full、upgrade）")
    if not FULL_SCHEMA.is_file():
        die(f"缺少全量 SQL: {FULL_SCHEMA}")
    if not MIGRATIONS_DIR.is_dir():
        die(f"缺少增量 SQL 目录: {MIGRATIONS_DIR}")

    config = load_config()
    database = config["database"]

    server_connection = connect(config)
    try:
        exists = database_exists(server_connection, database)
        initialized = exists and schema_initialized(server_connection, database)
        if mode == "auto":
            mode = "upgrade" if initialized else "full"
        if mode == "full":
            create_database(server_connection, database)
        elif not exists:
            die(f"数据库 {database} 不存在，请先使用 full 或 auto 模式")
    finally:
        server_connection.close()

    database_connection = connect(config, database)
    try:
        if mode == "full":
            log(f"执行当前版本全量 SQL: {FULL_SCHEMA}")
            execute_script(database_connection, FULL_SCHEMA)
        run_incremental_migrations(database_connection)
    finally:
        database_connection.close()

    log(f"数据库部署完成（模式: {mode}，执行器: PyMySQL）")


if __name__ == "__main__":
    main()
