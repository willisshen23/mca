from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from src.secrets import load_master_key, maybe_decrypt, looks_encrypted

logger = logging.getLogger("njbank.agent")

AGENT_NAMES = [
    "supervisor",
    # report pipeline 仍在使用的角色
    "data_analysis",
    "report_generation",
    "report_validation",
    "finalize",
    # agent_v2 多模型路由角色
    "agent_v2_main",
    "agent_v2_cheap",
    "agent_v2_fallback",
]


def _agent_field(name: str, suffix: str, default: str = "") -> Field:
    env_name = f"{name.upper()}_LLM_{suffix.upper()}"
    return Field(default=default, alias=env_name)


def _agent_max_tokens_field(name: str) -> Field:
    return Field(default=0, ge=0, alias=f"{name.upper()}_LLM_MAX_TOKENS")


# 所有可能存密文的 API Key 字段（全局 + 各角色），供解密 validator 使用。
_API_KEY_FIELDS = ["llm_api_key"] + [f"{name}_llm_api_key" for name in AGENT_NAMES]

# 主密钥默认文件（与密文 .env 物理分离；backend/data/ 已在 .gitignore）
_DEFAULT_MASTER_KEY_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "secrets" / "master.key"
)


class Settings(BaseSettings):
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    llm_max_tokens: int = Field(default=262144, ge=1, alias="LLM_MAX_TOKENS")

    supervisor_llm_api_key: str = _agent_field("supervisor", "api_key")
    supervisor_llm_base_url: str = _agent_field("supervisor", "base_url")
    supervisor_llm_model: str = _agent_field("supervisor", "model")
    supervisor_llm_max_tokens: int = _agent_max_tokens_field("supervisor")
    # LLM 单次请求超时（秒），作用于所有 Agent 的 LLM 客户端。
    # 需小于 nginx proxy_read_timeout（600s），否则网关会先断连。
    llm_timeout_seconds: float = Field(default=600, alias="LLM_TIMEOUT_SECONDS")
    # 是否校验大模型端点 SSL 证书。openjiuwen develop 版要求 verify_ssl=True 时
    # 必须提供 ssl_cert 文件路径，否则建 client 直接报错；内网/自签端点默认关闭。
    llm_verify_ssl: bool = Field(default=False, alias="LLM_VERIFY_SSL")

    data_analysis_llm_api_key: str = _agent_field("data_analysis", "api_key")
    data_analysis_llm_base_url: str = _agent_field("data_analysis", "base_url")
    data_analysis_llm_model: str = _agent_field("data_analysis", "model")
    data_analysis_llm_max_tokens: int = _agent_max_tokens_field("data_analysis")

    report_generation_llm_api_key: str = _agent_field("report_generation", "api_key")
    report_generation_llm_base_url: str = _agent_field("report_generation", "base_url")
    report_generation_llm_model: str = _agent_field("report_generation", "model")
    report_generation_llm_max_tokens: int = _agent_max_tokens_field("report_generation")

    report_validation_llm_api_key: str = _agent_field("report_validation", "api_key")
    report_validation_llm_base_url: str = _agent_field("report_validation", "base_url")
    report_validation_llm_model: str = _agent_field("report_validation", "model")
    report_validation_llm_max_tokens: int = _agent_max_tokens_field("report_validation")

    finalize_llm_api_key: str = _agent_field("finalize", "api_key")
    finalize_llm_base_url: str = _agent_field("finalize", "base_url")
    finalize_llm_model: str = _agent_field("finalize", "model")
    finalize_llm_max_tokens: int = _agent_max_tokens_field("finalize")
    # 每次调用为模型输出预留的默认空间。
    llm_output_token_reserve: int = Field(
        default=16384,
        ge=0,
        alias="LLM_OUTPUT_TOKEN_RESERVE",
    )

    # ── agent_v2 多模型路由角色（字段名保留，agent_v3/agent_factory 在读） ──
    # 主推理模型（首轮/复杂请求）
    agent_v2_main_llm_api_key: str = _agent_field("agent_v2_main", "api_key")
    agent_v2_main_llm_base_url: str = _agent_field("agent_v2_main", "base_url")
    agent_v2_main_llm_model: str = _agent_field("agent_v2_main", "model")
    agent_v2_main_llm_max_tokens: int = _agent_max_tokens_field("agent_v2_main")
    # 轻量模型（短确认/闲聊）
    agent_v2_cheap_llm_api_key: str = _agent_field("agent_v2_cheap", "api_key")
    agent_v2_cheap_llm_base_url: str = _agent_field("agent_v2_cheap", "base_url")
    agent_v2_cheap_llm_model: str = _agent_field("agent_v2_cheap", "model")
    agent_v2_cheap_llm_max_tokens: int = _agent_max_tokens_field("agent_v2_cheap")
    # 降级备选模型（主模型调用异常时使用）
    agent_v2_fallback_llm_api_key: str = _agent_field("agent_v2_fallback", "api_key")
    agent_v2_fallback_llm_base_url: str = _agent_field("agent_v2_fallback", "base_url")
    agent_v2_fallback_llm_model: str = _agent_field("agent_v2_fallback", "model")
    agent_v2_fallback_llm_max_tokens: int = _agent_max_tokens_field("agent_v2_fallback")
    # agent_v2 历史摘要触发阈值（tokens，预留）
    agent_v2_summary_max_tokens: int = Field(default=120000, alias="AGENT_V2_SUMMARY_MAX_TOKENS")
    agent_v2_recursion_limit: int = Field(
        default=50,
        ge=1,
        alias="AGENT_V2_RECURSION_LIMIT",
    )

    # ── agent_v3 (openJiuwen agent-core，唯一运行时) ──
    agent_v3_max_iterations: int = Field(
        default=50,
        ge=1,
        alias="AGENT_V3_MAX_ITERATIONS",
    )
    # v3 持久化 checkpointer 的 SQLite 文件（与 v2 的 data/checkpoints.db 物理隔离）；
    # 后续迁 MySQL 时改走 conf.db_client 通道，本项失效
    agent_v3_checkpointer_db_path: str = Field(
        default="data/v3_checkpoints.db",
        alias="AGENT_V3_CHECKPOINTER_DB_PATH",
    )

    db_path: str = Field(default="data/checkpoints.db", alias="DB_PATH")
    business_database_url: str = Field(
        default="sqlite:///data/skills.db",
        alias="BUSINESS_DATABASE_URL",
    )
    database_host: str = Field(default="", alias="DATABASE_HOST")
    database_port: str = Field(default="", alias="DATABASE_PORT")
    database_username: str = Field(default="", alias="DATABASE_USERNAME")
    database_password: str = Field(default="", alias="DATABASE_PASSWORD")
    database_name: str = Field(default="", alias="DATABASE_NAME")
    upload_dir: str = Field(default="data/uploads", alias="UPLOAD_DIR")
    output_dir: str = Field(default="data/outputs", alias="OUTPUT_DIR")
    report_export_dir: str = Field(default="data/outputs/exports", alias="REPORT_EXPORT_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_to_file: bool = Field(default=True, alias="LOG_TO_FILE")
    log_dir: str = Field(default="data/logs", alias="LOG_DIR")
    # 日志基名，实际文件会带上日期，如 app-2026-06-25.log
    log_file: str = Field(default="app.log", alias="LOG_FILE")
    # 按天轮转后保留的日志文件数量（天数）
    log_file_backup_count: int = Field(default=30, alias="LOG_FILE_BACKUP_COUNT")

    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://159.1.56.109:8080",
        alias="ALLOWED_ORIGINS",
    )
    max_upload_size_mb: int = Field(default=50, alias="MAX_UPLOAD_SIZE_MB")
    report_html_guard_max_retries: int = Field(default=1, alias="REPORT_HTML_GUARD_MAX_RETRIES")

    bank_marketing_api_token: str = Field(default="", alias="BANK_MARKETING_API_TOKEN")
    bank_marketing_api_timeout_seconds: int = Field(
        default=10,
        alias="BANK_MARKETING_API_TIMEOUT_SECONDS",
    )
    # 每个外部接口都单独配置完"URL（含协议、主机、端口、路径）
    bank_marketing_activity_list_url: str = Field(
        default="http://localhost:8005/api2/campaigns/search",
        alias="BANK_MARKETING_ACTIVITY_LIST_URL",
    )
    bank_marketing_activity_list_method: str = Field(
        default="POST",
        alias="BANK_MARKETING_ACTIVITY_LIST_METHOD",
    )
    bank_marketing_activity_src_sys_no: str = Field(
        default="P10",
        alias="BANK_MARKETING_ACTIVITY_SRC_SYS_NO",
    )
    bank_marketing_template_list_url: str = Field(
        default="http://localhost:8005/api2/templates",
        alias="BANK_MARKETING_TEMPLATE_LIST_URL",
    )
    bank_marketing_template_list_method: str = Field(
        default="POST",
        alias="BANK_MARKETING_TEMPLATE_LIST_METHOD",
    )
    bank_marketing_component_values_url: str = Field(
        default="http://localhost:8005/api2/component-values",
        alias="BANK_MARKETING_COMPONENT_VALUES_URL",
    )
    bank_marketing_component_values_method: str = Field(
        default="POST",
        alias="BANK_MARKETING_COMPONENT_VALUES_METHOD",
    )
    bank_marketing_data_template_match_top_n: int = Field(
        default=2,
        alias="BANK_MARKETING_DATA_TEMPLATE_MATCH_TOP_N",
    )
    bank_marketing_outbound_activity_data_url: str = Field(
        default="http://localhost:8005/api2/dataservice/query/{trade_code}",
        alias="BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL",
    )
    bank_marketing_outbound_activity_data_method: str = Field(
        default="POST",
        alias="BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_METHOD",
    )
    bank_marketing_outbound_activity_trade_codes: str = Field(
        default=(
            "EDW_RTL_MED_ASSET_CONVERSION,"
            "EDW_RTL_MED_PRODUCT_TRANSACTION,"
            "EDW_RTL_MED_ACTIVITY_BASE_INFO,"
            "EDW_RTL_MED_OUTBOUND_CALL_EXECUTION,"
            "EDW_RTL_MED_SOURCE_OF_PRODUCT_VALIDCALL"
        ),
        alias="BANK_MARKETING_OUTBOUND_ACTIVITY_TRADE_CODES",
    )
    bank_marketing_default_channel: str = Field(
        default="MF0",
        alias="BANK_MARKETING_DEFAULT_CHANNEL",
    )
    bank_marketing_default_user_id: str = Field(
        default="1011273",
        alias="BANK_MARKETING_DEFAULT_USER_ID",
    )
    bank_marketing_default_org_no: str = Field(
        default="001",
        alias="BANK_MARKETING_DEFAULT_ORG_NO",
    )

    @field_validator(*_API_KEY_FIELDS, mode="before")
    @classmethod
    def _decrypt_llm_api_keys(cls, v: object) -> object:
        """env 值若为 enc:v1: 密文则在加载时解密，明文原样透传。

        主密钥经 src.secrets.load_master_key 读取（进程环境变量或密钥文件），
        不与密文同存 backend/.env。密文缺主密钥时抛 MasterKeyMissingError，
        进程启动即失败，避免把密文当明文发给上游。
        """
        if isinstance(v, str) and looks_encrypted(v):
            master_key = load_master_key(default_key_file=_DEFAULT_MASTER_KEY_FILE)
            return maybe_decrypt(v, master_key)
        return v

    model_config = {
        "env_file": str(Path(__file__).resolve().parent.parent / ".env"),
        "env_file_encoding": "utf-8",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()


def resolve_path(relative: str) -> Path:
    root = Path(__file__).resolve().parent.parent
    return root / relative


def extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1)
    text = text.strip()
    return json.loads(text)

