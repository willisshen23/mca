from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from src.secrets import load_master_key, maybe_decrypt

_OPS_DIR = Path(__file__).resolve().parents[1]

_BANK_URL_KEYS = (
    "BANK_MARKETING_ACTIVITY_LIST_URL",
    "BANK_MARKETING_TEMPLATE_LIST_URL",
    "BANK_MARKETING_COMPONENT_VALUES_URL",
    "BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL",
)


@dataclass
class Settings:
    main_app_dir: Path
    main_health_url: str
    main_pid_file: Path
    log_dir: Path
    ops_db_path: Path
    seed_runbook_dir: Path
    log_window_hours: int = 6
    disk_warn_pct: float = 85.0
    disk_red_pct: float = 95.0
    llm_latency_warn_s: float = 10.0
    llm_latency_red_s: float = 30.0
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_s: float = 60.0
    evidence_token_budget: int = 12000
    db_host: str = ""
    db_port: int = 3306
    db_user: str = ""
    db_password: str = ""
    db_name: str = ""
    bank_api_urls: list[str] = field(default_factory=list)
    bank_api_token: str = ""
    inspect_interval_minutes: int = 30
    snapshot_retention_days: int = 7
    collector_timeout_s: float = 5.0
    ops_token: str = ""


def load_settings(env_file=None, environ=None) -> Settings:
    """加载配置：OPS_* 优先，其次主应用 backend/.env，最后默认值。

    environ 仅供测试注入（传 {} 表示忽略进程环境变量）。
    """
    environ = os.environ if environ is None else environ
    env_file = Path(env_file) if env_file else _OPS_DIR / ".env"
    ops_env = {k: v for k, v in dotenv_values(env_file).items() if v is not None}

    def ops_get(key: str, default: str = "") -> str:
        return environ.get(key) or ops_env.get(key) or default

    main_app_dir = Path(ops_get("OPS_MAIN_APP_DIR") or (_OPS_DIR.parent / "backend"))
    main_env_raw = dotenv_values(main_app_dir / ".env")
    main_env = {k: v for k, v in main_env_raw.items() if v is not None}

    def main_get(key: str, default: str = "") -> str:
        return main_env.get(key) or default

    port = main_get("PORT", "8000")
    bank_urls = [main_env[k] for k in _BANK_URL_KEYS if main_env.get(k)]

    return Settings(
        main_app_dir=main_app_dir,
        main_health_url=ops_get("OPS_MAIN_HEALTH_URL", f"http://127.0.0.1:{port}/health"),
        main_pid_file=Path(ops_get("OPS_MAIN_PID_FILE") or (main_app_dir / "data" / "run" / "activity-analysis-assistant.pid")),
        log_dir=Path(ops_get("OPS_LOG_DIR") or (main_app_dir / "data" / "logs")),
        ops_db_path=Path(ops_get("OPS_DB_PATH") or (_OPS_DIR / "data" / "ops.db")),
        seed_runbook_dir=Path(ops_get("OPS_SEED_RUNBOOK_DIR") or (_OPS_DIR / "runbooks" / "seed")),
        log_window_hours=int(ops_get("OPS_LOG_WINDOW_HOURS", "6")),
        llm_base_url=ops_get("OPS_LLM_BASE_URL", main_get("LLM_BASE_URL")),
        llm_api_key=maybe_decrypt(
            ops_get("OPS_LLM_API_KEY", main_get("LLM_API_KEY")),
            load_master_key(
                environ,
                default_key_file=main_app_dir / "data" / "secrets" / "master.key",
            ),
        ),
        llm_model=ops_get("OPS_LLM_MODEL", main_get("LLM_MODEL")),
        llm_timeout_s=float(ops_get("OPS_LLM_TIMEOUT_SECONDS", main_get("LLM_TIMEOUT_SECONDS", "60"))),
        evidence_token_budget=int(ops_get("OPS_EVIDENCE_TOKEN_BUDGET", "12000")),
        db_host=main_get("DATABASE_HOST"),
        db_port=int(main_get("DATABASE_PORT", "3306") or "3306"),
        db_user=main_get("DATABASE_USERNAME"),
        db_password=main_get("DATABASE_PASSWORD"),
        db_name=main_get("DATABASE_NAME"),
        bank_api_urls=bank_urls,
        bank_api_token=main_get("BANK_MARKETING_API_TOKEN"),
        inspect_interval_minutes=int(ops_get("OPS_INSPECT_INTERVAL_MINUTES", "30")),
        ops_token=ops_get("OPS_TOKEN"),
    )
