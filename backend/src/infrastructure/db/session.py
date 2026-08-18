from __future__ import annotations

from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import Session, sessionmaker


def get_database_url() -> str:
    try:
        from src.config import get_settings

        settings = get_settings()
    except Exception:
        settings = None

    def configured_value(env_key: str, setting_name: str, default: str = "") -> str:
        value = os.getenv(env_key)
        if value is None and settings is not None:
            value = getattr(settings, setting_name, default)
        return str(value or default).strip()

    database_host = configured_value("DATABASE_HOST", "database_host")
    if database_host:
        database_fields = {
            "DATABASE_HOST": database_host,
            "DATABASE_PORT": configured_value("DATABASE_PORT", "database_port"),
            "DATABASE_USERNAME": configured_value("DATABASE_USERNAME", "database_username"),
            "DATABASE_PASSWORD": configured_value("DATABASE_PASSWORD", "database_password"),
            "DATABASE_NAME": configured_value("DATABASE_NAME", "database_name"),
        }
        missing_fields = [key for key, value in database_fields.items() if not value]
        if missing_fields:
            raise ValueError(
                "MySQL configuration is incomplete; missing: " + ", ".join(missing_fields)
            )
        try:
            port = int(database_fields["DATABASE_PORT"])
        except ValueError as exc:
            raise ValueError("DATABASE_PORT must be an integer between 1 and 65535") from exc
        if not 1 <= port <= 65535:
            raise ValueError("DATABASE_PORT must be an integer between 1 and 65535")
        return URL.create(
            drivername="mysql+pymysql",
            username=database_fields["DATABASE_USERNAME"],
            password=database_fields["DATABASE_PASSWORD"],
            host=database_fields["DATABASE_HOST"],
            port=port,
            database=database_fields["DATABASE_NAME"],
            query={"charset": "utf8mb4"},
        ).render_as_string(hide_password=False)

    url = os.getenv("BUSINESS_DATABASE_URL")
    if not url:
        url = settings.business_database_url if settings is not None else "sqlite:///data/skills.db"
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        db_path = url.removeprefix("sqlite:///")
        root = Path(__file__).resolve().parents[3]
        absolute_path = root / db_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{absolute_path}"
    parsed_url = make_url(url)
    if parsed_url.drivername in {"mysql", "mysql+pymysql"}:
        # PyMySQL is the supported MySQL driver for both online and offline
        # deployments. Use utf8mb4 unless the connection URL overrides it.
        query = dict(parsed_url.query)
        query.setdefault("charset", "utf8mb4")
        parsed_url = parsed_url.set(drivername="mysql+pymysql", query=query)
    return parsed_url.render_as_string(hide_password=False)


def create_db_engine(url: str | None = None) -> Engine:
    database_url = get_database_url() if url is None else url
    parsed_url = make_url(database_url)
    if parsed_url.drivername in {"mysql", "mysql+pymysql"}:
        query = dict(parsed_url.query)
        query.setdefault("charset", "utf8mb4")
        database_url = parsed_url.set(
            drivername="mysql+pymysql",
            query=query,
        ).render_as_string(hide_password=False)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine_options: dict[str, object] = {
        "pool_pre_ping": True,
        "connect_args": connect_args,
    }
    if database_url.startswith("mysql+pymysql"):
        # Recycle idle connections before common MySQL wait_timeout values.
        engine_options["pool_recycle"] = 1800
    return create_engine(database_url, **engine_options)


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
