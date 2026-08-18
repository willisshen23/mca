from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import math
from pathlib import Path
import re
import sqlite3
from typing import Any, TextIO

import pymysql


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = BACKEND_DIR / "data" / "skills.db"
DEFAULT_OUTPUT = BACKEND_DIR.parent / "data" / "mysql" / "sqlite_export.sql"
MAX_INSERT_CHARS = 1_000_000

# MySQL connection used by direct migration. Edit these values when the target
# database changes. The password is intentionally stored here per deployment
# requirements, so restrict access to this file.
DATABASE_CONFIG = {
    "host": "115.120.56.112",
    "port": 3306,
    "username": "nj_bank",
    "password": "NJ_bank123!@#",
    "database": "njbank_aa",
}


def mysql_identifier(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def sqlite_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def safe_object_name(prefix: str, *parts: str) -> str:
    raw = "_".join((prefix, *parts))
    cleaned = re.sub(r"[^A-Za-z0-9_$]", "_", raw)
    if len(cleaned) <= 64:
        return cleaned
    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:10]
    return cleaned[:53] + "_" + digest


def mysql_type(declared_type: str) -> str:
    value = (declared_type or "").strip().upper()
    if not value:
        return "LONGTEXT"
    sized = re.fullmatch(r"(VAR)?CHAR\s*\(\s*(\d+)\s*\)", value)
    if sized:
        kind = "VARCHAR" if sized.group(1) else "CHAR"
        return f"{kind}({sized.group(2)})"
    decimal = re.fullmatch(r"(?:DECIMAL|NUMERIC)\s*\((\d+)\s*,\s*(\d+)\)", value)
    if decimal:
        return f"DECIMAL({decimal.group(1)},{decimal.group(2)})"
    if "BOOL" in value:
        return "TINYINT(1)"
    if "INT" in value:
        return "INTEGER"
    if any(token in value for token in ("REAL", "FLOA", "DOUB")):
        return "DOUBLE"
    if any(token in value for token in ("DEC", "NUM")):
        return "DECIMAL(65,30)"
    if "DATETIME" in value or "TIMESTAMP" in value:
        return "DATETIME"
    if value == "DATE":
        return "DATE"
    if value == "TIME":
        return "TIME"
    if "JSON" in value:
        return "JSON"
    if "BLOB" in value or value == "BINARY":
        return "LONGBLOB"
    if "CHAR" in value or "CLOB" in value or "TEXT" in value:
        return "LONGTEXT"
    return "LONGTEXT"


def mysql_default(value: Any, target_type: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    upper = text.upper()
    if upper in {"NULL", "CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME"}:
        return upper
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return text
    if target_type not in {"TEXT", "LONGTEXT", "LONGBLOB", "JSON"}:
        if len(text) >= 2 and text[0] == text[-1] == "'":
            return text
        if len(text) >= 2 and text[0] == text[-1] == '"':
            inner = text[1:-1].replace("'", "''")
            return f"'{inner}'"
    return None


def normalize_datetime(value: Any) -> Any:
    if value is None or isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return value
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.isoformat(sep=" ", timespec="microseconds").rstrip("0").rstrip(".")


def mysql_literal(value: Any, target_type: str) -> str:
    if value is None:
        return "NULL"
    if target_type == "DATETIME":
        value = normalize_datetime(value)
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"MySQL cannot represent non-finite float: {value!r}")
        return repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return "0x" + raw.hex().upper() if raw else "X''"
    raw = str(value).encode("utf-8")
    if not raw:
        return "''"
    return "CONVERT(0x" + raw.hex().upper() + " USING utf8mb4)"


def list_tables(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]


def foreign_keys(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    grouped: dict[int, list[sqlite3.Row]] = defaultdict(list)
    rows = connection.execute(
        f"PRAGMA foreign_key_list({sqlite_identifier(table)})"
    ).fetchall()
    for row in rows:
        grouped[int(row[0])].append(row)
    result: list[dict[str, Any]] = []
    for fk_id, items in sorted(grouped.items()):
        items.sort(key=lambda item: int(item[1]))
        result.append(
            {
                "id": fk_id,
                "table": str(items[0][2]),
                "from": [str(item[3]) for item in items],
                "to": [str(item[4]) for item in items],
                "on_update": str(items[0][5]).upper(),
                "on_delete": str(items[0][6]).upper(),
            }
        )
    return result


def order_tables(connection: sqlite3.Connection, tables: list[str]) -> list[str]:
    remaining = set(tables)
    ordered: list[str] = []
    while remaining:
        ready = []
        for table in sorted(remaining):
            dependencies = {
                fk["table"] for fk in foreign_keys(connection, table)
                if fk["table"] != table and fk["table"] in remaining
            }
            if not dependencies:
                ready.append(table)
        if not ready:
            ordered.extend(sorted(remaining))
            break
        for table in ready:
            ordered.append(table)
            remaining.remove(table)
    return ordered


def index_definitions(
    connection: sqlite3.Connection, table: str
) -> tuple[list[tuple[str, list[str]]], list[tuple[str, list[str]]]]:
    unique_indexes: list[tuple[str, list[str]]] = []
    normal_indexes: list[tuple[str, list[str]]] = []
    for row in connection.execute(f"PRAGMA index_list({sqlite_identifier(table)})"):
        name = str(row[1])
        is_unique = bool(row[2])
        origin = str(row[3]) if len(row) > 3 else ""
        is_partial = bool(row[4]) if len(row) > 4 else False
        if origin == "pk" or is_partial:
            continue
        columns = [
            str(info[2])
            for info in connection.execute(f"PRAGMA index_info({sqlite_identifier(name)})")
            if info[2] is not None
        ]
        if not columns:
            continue
        target = unique_indexes if is_unique else normal_indexes
        target.append((name, columns))
    return unique_indexes, normal_indexes


def create_table_sql(connection: sqlite3.Connection, table: str) -> tuple[str, dict[str, str]]:
    columns = connection.execute(f"PRAGMA table_info({sqlite_identifier(table)})").fetchall()
    pk_columns = [str(row[1]) for row in sorted(columns, key=lambda row: int(row[5])) if row[5]]
    auto_increment = (
        len(pk_columns) == 1
        and any(str(row[1]) == pk_columns[0] and "INT" in str(row[2]).upper() for row in columns)
    )
    definitions: list[str] = []
    column_types: dict[str, str] = {}
    for row in columns:
        name = str(row[1])
        target_type = mysql_type(str(row[2] or ""))
        column_types[name] = target_type
        parts = [mysql_identifier(name), target_type]
        if bool(row[3]) or bool(row[5]):
            parts.append("NOT NULL")
        default = mysql_default(row[4], target_type)
        if default is not None:
            parts.extend(("DEFAULT", default))
        if auto_increment and name == pk_columns[0]:
            parts.append("AUTO_INCREMENT")
        definitions.append("    " + " ".join(parts))

    if pk_columns:
        definitions.append(
            "    PRIMARY KEY (" + ", ".join(mysql_identifier(col) for col in pk_columns) + ")"
        )
    unique_indexes, _ = index_definitions(connection, table)
    for index_name, index_columns in unique_indexes:
        name = safe_object_name("uq", table, index_name)
        definitions.append(
            f"    CONSTRAINT {mysql_identifier(name)} UNIQUE ("
            + ", ".join(mysql_identifier(col) for col in index_columns)
            + ")"
        )
    for fk in foreign_keys(connection, table):
        name = safe_object_name("fk", table, str(fk["id"]), *fk["from"])
        clause = (
            f"    CONSTRAINT {mysql_identifier(name)} FOREIGN KEY ("
            + ", ".join(mysql_identifier(col) for col in fk["from"])
            + f") REFERENCES {mysql_identifier(fk['table'])} ("
            + ", ".join(mysql_identifier(col) for col in fk["to"])
            + ")"
        )
        if fk["on_delete"] not in {"", "NO ACTION"}:
            clause += f" ON DELETE {fk['on_delete']}"
        if fk["on_update"] not in {"", "NO ACTION"}:
            clause += f" ON UPDATE {fk['on_update']}"
        definitions.append(clause)

    sql = (
        f"CREATE TABLE {mysql_identifier(table)} (\n"
        + ",\n".join(definitions)
        + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n"
    )
    return sql, column_types


def write_indexes(output: TextIO, connection: sqlite3.Connection, table: str) -> None:
    for statement in index_statements(connection, table):
        output.write(statement + "\n")


def index_statements(connection: sqlite3.Connection, table: str) -> list[str]:
    statements: list[str] = []
    _, normal_indexes = index_definitions(connection, table)
    for index_name, columns in normal_indexes:
        name = safe_object_name("ix", table, index_name)
        statements.append(
            f"CREATE INDEX {mysql_identifier(name)} ON {mysql_identifier(table)} ("
            + ", ".join(mysql_identifier(col) for col in columns)
            + ");"
        )
    return statements


def write_table_data(
    output: TextIO,
    connection: sqlite3.Connection,
    table: str,
    column_types: dict[str, str],
) -> int:
    cursor = connection.execute(f"SELECT * FROM {sqlite_identifier(table)}")
    columns = [str(item[0]) for item in cursor.description or []]
    if not columns:
        return 0
    prefix = (
        f"INSERT INTO {mysql_identifier(table)} ("
        + ", ".join(mysql_identifier(column) for column in columns)
        + ") VALUES\n"
    )
    pending: list[str] = []
    pending_chars = len(prefix)
    count = 0
    for row in cursor:
        row_sql = "(" + ", ".join(
            mysql_literal(value, column_types[column])
            for column, value in zip(columns, row)
        ) + ")"
        if pending and pending_chars + len(row_sql) + 3 > MAX_INSERT_CHARS:
            output.write(prefix + ",\n".join(pending) + ";\n")
            pending = []
            pending_chars = len(prefix)
        pending.append(row_sql)
        pending_chars += len(row_sql) + 2
        count += 1
    if pending:
        output.write(prefix + ",\n".join(pending) + ";\n")
    return count


def export(sqlite_path: Path, output_path: Path, database: str | None) -> tuple[int, int]:
    connection = sqlite3.connect(sqlite_path)
    connection.row_factory = sqlite3.Row
    try:
        tables = order_tables(connection, list_tables(connection))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="\n") as output:
            output.write(
                "-- MySQL 8.0+ dump generated from SQLite.\n"
                f"-- Source: {sqlite_path.as_posix()}\n"
                "SET NAMES utf8mb4;\n"
                "SET FOREIGN_KEY_CHECKS = 0;\n"
                "SET UNIQUE_CHECKS = 0;\n"
            )
            if database:
                if not re.fullmatch(r"[A-Za-z0-9_$]+", database):
                    raise ValueError("Database name may only contain letters, digits, _, and $")
                output.write(
                    f"CREATE DATABASE IF NOT EXISTS {mysql_identifier(database)} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
                    f"USE {mysql_identifier(database)};\n"
                )
            output.write("\n")
            for table in reversed(tables):
                output.write(f"DROP TABLE IF EXISTS {mysql_identifier(table)};\n")
            output.write("\n")

            table_types: dict[str, dict[str, str]] = {}
            for table in tables:
                ddl, types = create_table_sql(connection, table)
                table_types[table] = types
                output.write(ddl + "\n")
            for table in tables:
                write_indexes(output, connection, table)

            output.write("\nSTART TRANSACTION;\n")
            total_rows = 0
            for table in tables:
                output.write(f"\n-- Data for {mysql_identifier(table)}\n")
                count = write_table_data(output, connection, table, table_types[table])
                output.write(f"-- {count} row(s) exported.\n")
                total_rows += count
            output.write(
                "\nCOMMIT;\n"
                "SET UNIQUE_CHECKS = 1;\n"
                "SET FOREIGN_KEY_CHECKS = 1;\n"
            )
        return len(tables), total_rows
    finally:
        connection.close()


def direct_value(value: Any, target_type: str) -> Any:
    if target_type == "DATETIME":
        return normalize_datetime(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    return value


def migrate_directly(
    sqlite_path: Path,
    database_override: str | None = None,
) -> tuple[int, int]:
    config = dict(DATABASE_CONFIG)
    if database_override:
        config["database"] = database_override
    required = ("host", "port", "username", "password", "database")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError("Missing database configuration: " + ", ".join(missing))
    try:
        port = int(config["port"])
    except ValueError as exc:
        raise ValueError("DATABASE_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("DATABASE_PORT must be between 1 and 65535")

    sqlite_connection = sqlite3.connect(sqlite_path)
    sqlite_connection.row_factory = sqlite3.Row
    mysql_connection = pymysql.connect(
        host=config["host"],
        port=port,
        user=config["username"],
        password=config["password"],
        database=config["database"],
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
        read_timeout=120,
        write_timeout=120,
    )
    try:
        tables = order_tables(sqlite_connection, list_tables(sqlite_connection))
        table_types: dict[str, dict[str, str]] = {}
        with mysql_connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            for table in reversed(tables):
                cursor.execute(f"DROP TABLE IF EXISTS {mysql_identifier(table)}")
            for table in tables:
                ddl, types = create_table_sql(sqlite_connection, table)
                table_types[table] = types
                cursor.execute(ddl)
            for table in tables:
                for statement in index_statements(sqlite_connection, table):
                    cursor.execute(statement)
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        total_rows = 0
        mysql_connection.begin()
        try:
            with mysql_connection.cursor() as cursor:
                for table in tables:
                    source_cursor = sqlite_connection.execute(
                        f"SELECT * FROM {sqlite_identifier(table)}"
                    )
                    columns = [str(item[0]) for item in source_cursor.description or []]
                    if not columns:
                        continue
                    placeholders = ", ".join(["%s"] * len(columns))
                    insert_sql = (
                        f"INSERT INTO {mysql_identifier(table)} ("
                        + ", ".join(mysql_identifier(column) for column in columns)
                        + f") VALUES ({placeholders})"
                    )
                    while True:
                        batch = source_cursor.fetchmany(200)
                        if not batch:
                            break
                        values = [
                            tuple(
                                direct_value(value, table_types[table][column])
                                for column, value in zip(columns, row)
                            )
                            for row in batch
                        ]
                        cursor.executemany(insert_sql, values)
                        total_rows += len(values)
            mysql_connection.commit()
        except Exception:
            mysql_connection.rollback()
            raise

        with mysql_connection.cursor() as cursor:
            for table in tables:
                source_count = sqlite_connection.execute(
                    f"SELECT COUNT(*) FROM {sqlite_identifier(table)}"
                ).fetchone()[0]
                cursor.execute(f"SELECT COUNT(*) FROM {mysql_identifier(table)}")
                target_count = cursor.fetchone()[0]
                if source_count != target_count:
                    raise RuntimeError(
                        f"Row count mismatch for {table}: SQLite={source_count}, MySQL={target_count}"
                    )
        return len(tables), total_rows
    finally:
        try:
            with mysql_connection.cursor() as cursor:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        finally:
            mysql_connection.close()
            sqlite_connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate SQLite directly to the MySQL DATABASE_CONFIG in this script. "
            "Use --output only when an SQL dump file is needed."
        )
    )
    parser.add_argument("--sqlite", type=Path, default=DEFAULT_SQLITE)
    parser.add_argument(
        "--output",
        type=Path,
        help=f"Export SQL instead of migrating directly (default path: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--database",
        help="Override DATABASE_CONFIG['database']; also used by SQL export CREATE/USE.",
    )
    args = parser.parse_args()
    if not args.sqlite.is_file():
        raise FileNotFoundError(args.sqlite)
    if args.output:
        table_count, row_count = export(args.sqlite, args.output, args.database)
        print(f"Exported {table_count} table(s), {row_count} row(s) to {args.output}")
    else:
        table_count, row_count = migrate_directly(args.sqlite, args.database)
        print(f"Migrated {table_count} table(s), {row_count} row(s) directly to MySQL")


if __name__ == "__main__":
    main()
