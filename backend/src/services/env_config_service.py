from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.config import get_settings


def _reset_llm_caches() -> None:
    """配置变更后清空 LLM 客户端缓存（延迟 import 避免环）。"""
    from src.llm import reset_model_cache

    reset_model_cache()

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

ENV_GROUPS: list[dict[str, Any]] = [
    {
        "key": "llm",
        "name": "大模型配",
        "fields": [
            {"key": "LLM_BASE_URL", "label": "全局模型服务地址", "type": "text"},
            {"key": "LLM_MODEL", "label": "全局模型名称", "type": "text"},
            {"key": "LLM_MAX_TOKENS", "label": "全局模型最大 Tokens", "type": "number"},
            {"key": "LLM_API_KEY", "label": "全局 API Key", "type": "password", "secret": True},
            {"key": "LLM_TIMEOUT_SECONDS", "label": "LLM 请求超时(秒)", "type": "number"},
            {"key": "SUPERVISOR_LLM_BASE_URL", "label": "主管 Agent 服务地址", "type": "text"},
            {"key": "SUPERVISOR_LLM_MODEL", "label": "主管 Agent 模型", "type": "text"},
            {"key": "SUPERVISOR_LLM_MAX_TOKENS", "label": "主管 Agent 模型最大 Tokens", "type": "number"},
            {"key": "DATA_ANALYSIS_LLM_BASE_URL", "label": "数据分析 Agent 服务地址", "type": "text"},
            {"key": "DATA_ANALYSIS_LLM_MODEL", "label": "数据分析 Agent 模型", "type": "text"},
            {"key": "DATA_ANALYSIS_LLM_MAX_TOKENS", "label": "数据分析 Agent 模型最大 Tokens", "type": "number"},
            {"key": "REPORT_GENERATION_LLM_BASE_URL", "label": "报告生成 Agent 服务地址", "type": "text"},
            {"key": "REPORT_GENERATION_LLM_MODEL", "label": "报告生成 Agent 模型", "type": "text"},
            {"key": "REPORT_GENERATION_LLM_MAX_TOKENS", "label": "报告生成 Agent 模型最大 Tokens", "type": "number"},
            {"key": "LLM_OUTPUT_TOKEN_RESERVE", "label": "模型输出预留 Tokens", "type": "number"},
            {"key": "REPORT_VALIDATION_LLM_BASE_URL", "label": "报告校验 Agent 服务地址", "type": "text"},
            {"key": "REPORT_VALIDATION_LLM_MODEL", "label": "报告校验 Agent 模型", "type": "text"},
            {"key": "REPORT_VALIDATION_LLM_MAX_TOKENS", "label": "报告校验 Agent 模型最大 Tokens", "type": "number"},
            {"key": "FINALIZE_LLM_BASE_URL", "label": "汇Agent 服务地址", "type": "text"},
            {"key": "FINALIZE_LLM_MODEL", "label": "汇Agent 模型", "type": "text"},
            {"key": "FINALIZE_LLM_MAX_TOKENS", "label": "汇总 Agent 模型最大 Tokens", "type": "number"},
            {"key": "AGENT_V2_MAIN_LLM_BASE_URL", "label": "主推理模型服务地址", "type": "text"},
            {"key": "AGENT_V2_MAIN_LLM_MODEL", "label": "主推理模型名称", "type": "text"},
            {"key": "AGENT_V2_MAIN_LLM_MAX_TOKENS", "label": "主推理模型最大 Tokens", "type": "number"},
            {"key": "AGENT_V2_CHEAP_LLM_BASE_URL", "label": "轻量模型服务地址", "type": "text"},
            {"key": "AGENT_V2_CHEAP_LLM_MODEL", "label": "轻量模型名称", "type": "text"},
            {"key": "AGENT_V2_CHEAP_LLM_MAX_TOKENS", "label": "轻量模型最大 Tokens", "type": "number"},
            {"key": "AGENT_V2_FALLBACK_LLM_BASE_URL", "label": "降级模型服务地址", "type": "text"},
            {"key": "AGENT_V2_FALLBACK_LLM_MODEL", "label": "降级模型名称", "type": "text"},
            {"key": "AGENT_V2_FALLBACK_LLM_MAX_TOKENS", "label": "降级模型最大 Tokens", "type": "number"},
        ],
    },
    {
        "key": "system",
        "name": "系统运行配置",
        "fields": [
            {"key": "LOG_LEVEL", "label": "日志级别", "type": "select", "options": ["DEBUG", "INFO", "WARNING", "ERROR"]},
            {"key": "HOST", "label": "监听地址", "type": "text", "restart_required": True},
            {"key": "PORT", "label": "监听端口", "type": "number", "restart_required": True},
            {"key": "ALLOWED_ORIGINS", "label": "允许跨域来源", "type": "text"},
            {"key": "MAX_UPLOAD_SIZE_MB", "label": "最大上传大MB)", "type": "number"},
            {"key": "REPORT_HTML_GUARD_MAX_RETRIES", "label": "HTML报告检查重试次数", "type": "number"},
            {"key": "UPLOAD_DIR", "label": "上传目录", "type": "text"},
            {"key": "OUTPUT_DIR", "label": "输出目录", "type": "text"},
            {"key": "DB_PATH", "label": "检查点数据", "type": "text", "restart_required": True},
            {"key": "DATABASE_HOST", "label": "数据库 IP 地址", "type": "text", "restart_required": True},
            {"key": "DATABASE_PORT", "label": "数据库端口", "type": "number", "restart_required": True},
            {"key": "DATABASE_USERNAME", "label": "数据库用户名", "type": "text", "restart_required": True},
            {"key": "DATABASE_PASSWORD", "label": "数据库密码", "type": "password", "secret": True, "restart_required": True},
            {"key": "DATABASE_NAME", "label": "数据库名", "type": "text", "restart_required": True},
            {"key": "BACKEND_RESTART_COMMAND", "label": "后端重启命令", "type": "text"},
        ],
    },
    {
        "key": "bank_api",
        "name": "活动接口配置",
        "fields": [
            {"key": "BANK_MARKETING_API_TOKEN", "label": "活动接口 Token", "type": "password", "secret": True},
            {"key": "BANK_MARKETING_API_TIMEOUT_SECONDS", "label": "API timeout seconds", "type": "number"},
            {"key": "BANK_MARKETING_ACTIVITY_LIST_URL", "label": "活动列表接口完整URL", "type": "text"},
            {"key": "BANK_MARKETING_ACTIVITY_LIST_METHOD", "label": "活动列表方法", "type": "select", "options": ["GET", "POST"]},
            {"key": "BANK_MARKETING_ACTIVITY_SRC_SYS_NO", "label": "活动查询来源系统编号", "type": "text"},
            {"key": "BANK_MARKETING_TEMPLATE_LIST_URL", "label": "数据模板列表接口完整URL", "type": "text"},
            {"key": "BANK_MARKETING_TEMPLATE_LIST_METHOD", "label": "数据模板列表方法", "type": "select", "options": ["GET", "POST"]},
            {"key": "BANK_MARKETING_COMPONENT_VALUES_URL", "label": "组件数值接口完整URL", "type": "text"},
            {"key": "BANK_MARKETING_COMPONENT_VALUES_METHOD", "label": "组件数值方", "type": "select", "options": ["GET", "POST"]},
            {"key": "BANK_MARKETING_DATA_TEMPLATE_MATCH_TOP_N", "label": "数据模板匹配 TopN", "type": "number"},
            {"key": "BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL", "label": "外呼活动数据接口完整URL", "type": "text"},
            {"key": "BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_METHOD", "label": "外呼活动数据方法", "type": "select", "options": ["GET", "POST"]},
            {"key": "BANK_MARKETING_OUTBOUND_ACTIVITY_TRADE_CODES", "label": "外呼活动交易", "type": "textarea"},
            {"key": "BANK_MARKETING_DEFAULT_CHANNEL", "label": "默认渠道编码", "type": "text"},
            {"key": "BANK_MARKETING_DEFAULT_USER_ID", "label": "默认用户 ID", "type": "text"},
            {"key": "BANK_MARKETING_DEFAULT_ORG_NO", "label": "默认机构", "type": "text"},
        ],
    },
]

EDITABLE_FIELDS = {
    field["key"]: field
    for group in ENV_GROUPS
    for field in group["fields"]
}


def get_env_config() -> dict[str, Any]:
    values = _read_env_values()
    groups = []
    for group in ENV_GROUPS:
        fields = []
        for field in group["fields"]:
            value = values.get(field["key"], _settings_value(field["key"]))
            fields.append({**field, "value": value})
        groups.append({**group, "fields": fields})
    return {
        "env_path": str(ENV_PATH),
        "content": _read_env_content(),
        "restart_required": False,
        "groups": groups,
    }


def update_env_config(updates: dict[str, str]) -> dict[str, Any]:
    clean_updates: dict[str, str] = {}
    restart_required = False
    for key, value in updates.items():
        if key not in EDITABLE_FIELDS:
            raise ValueError(f"不允许修改配置项：{key}")
        clean_value = _normalize_value(key, value)
        clean_updates[key] = clean_value
        restart_required = restart_required or bool(EDITABLE_FIELDS[key].get("restart_required"))

    if clean_updates:
        _write_env_values(clean_updates)
        get_settings.cache_clear()
        _reset_llm_caches()

    payload = get_env_config()
    payload["restart_required"] = restart_required
    return payload


def update_env_config_content(content: str) -> dict[str, Any]:
    clean_content = _normalize_env_content(content)
    old_content = _read_env_content()
    changed = clean_content != old_content
    if changed:
        ENV_PATH.write_text(clean_content, encoding="utf-8")
        get_settings.cache_clear()
        _reset_llm_caches()

    payload = get_env_config()
    payload["restart_required"] = changed
    return payload


def _read_env_content() -> str:
    if not ENV_PATH.exists():
        return ""
    return ENV_PATH.read_text(encoding="utf-8")


def _normalize_env_content(content: str) -> str:
    text = str(content if content is not None else "")
    if "\x00" in text:
        raise ValueError(".env 内容不允许包含空字符")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text if not text or text.endswith("\n") else f"{text}\n"


def _read_env_values() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$", line)
        if not match:
            continue
        key, value = match.groups()
        values[key] = _strip_quotes(value)
    return values


def _write_env_values(updates: dict[str, str]) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen = set()
    updated_lines = []
    for line in lines:
        match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$", line)
        if match and match.group(2) in updates:
            indent, key, sep, _ = match.groups()
            updated_lines.append(f"{indent}{key}{sep}{_serialize_value(updates[key])}")
            seen.add(key)
        else:
            updated_lines.append(line)

    missing = [key for key in updates if key not in seen]
    if missing:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")
        updated_lines.append("# ============ 页面设置新增配置 ============")
        for key in missing:
            updated_lines.append(f"{key}={_serialize_value(updates[key])}")

    ENV_PATH.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")


def _normalize_value(key: str, value: Any) -> str:
    text = str(value if value is not None else "").strip()
    if "\n" in text or "\r" in text:
        raise ValueError(f"{key} 不允许包含换")
    field = EDITABLE_FIELDS[key]
    if field.get("type") == "number" and text:
        number = int(text)
        if key == "DATABASE_PORT" and not 1 <= number <= 65535:
            raise ValueError("DATABASE_PORT 必须是 1 到 65535 之间的整数")
        if key.endswith("LLM_MAX_TOKENS") and number < 1:
            raise ValueError(f"{key} 必须大于 0")
        if key == "LLM_OUTPUT_TOKEN_RESERVE" and number < 0:
            raise ValueError("LLM_OUTPUT_TOKEN_RESERVE 不能小于 0")
    options = field.get("options")
    if options and text and text.upper() not in options:
        raise ValueError(f"{key} 仅支持：{', '.join(options)}")
    return text.upper() if options and text else text


def _serialize_value(value: str) -> str:
    if value == "":
        return ""
    if any(char.isspace() for char in value) or "#" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return text


def _settings_value(env_key: str) -> str:
    settings = get_settings()
    mapping = {
        "LLM_API_KEY": "llm_api_key",
        "LLM_BASE_URL": "llm_base_url",
        "LLM_MODEL": "llm_model",
        "LOG_LEVEL": "log_level",
        "HOST": "host",
        "PORT": "port",
        "ALLOWED_ORIGINS": "allowed_origins",
        "MAX_UPLOAD_SIZE_MB": "max_upload_size_mb",
        "REPORT_HTML_GUARD_MAX_RETRIES": "report_html_guard_max_retries",
        "DB_PATH": "db_path",
        "DATABASE_HOST": "database_host",
        "DATABASE_PORT": "database_port",
        "DATABASE_USERNAME": "database_username",
        "DATABASE_PASSWORD": "database_password",
        "DATABASE_NAME": "database_name",
        "UPLOAD_DIR": "upload_dir",
        "OUTPUT_DIR": "output_dir",
    }
    if env_key.endswith("_LLM_API_KEY") or env_key.endswith("_LLM_BASE_URL") or env_key.endswith("_LLM_MODEL"):
        attr = env_key.lower()
    else:
        attr = mapping.get(env_key) or env_key.lower()
    return str(getattr(settings, attr, "") or "")
