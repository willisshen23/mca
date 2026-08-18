from __future__ import annotations

from pathlib import Path

from src.config import load_settings


def test_defaults_infer_main_app_env(tmp_path):
    main_app = tmp_path / "backend"
    main_app.mkdir()
    (main_app / ".env").write_text(
        "LLM_BASE_URL=http://gw:4000/v1\n"
        "LLM_API_KEY=sk-testkey123\n"
        "LLM_MODEL=deepseek\n"
        "PORT=8000\n"
        "DATABASE_HOST=10.0.0.1\n"
        "DATABASE_PORT=3307\n"
        "DATABASE_USERNAME=reader\n"
        "DATABASE_PASSWORD=pw\n"
        "DATABASE_NAME=coap\n"
        "BANK_MARKETING_API_TOKEN=tok\n"
        "BANK_MARKETING_ACTIVITY_LIST_URL=http://bank/api2/campaigns/search\n"
        "BANK_MARKETING_TEMPLATE_LIST_URL=http://bank/api2/templates\n"
        "BANK_MARKETING_COMPONENT_VALUES_URL=http://bank/api2/component-values\n"
        "BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL=http://bank/api2/dataservice/query/{trade_code}\n"
    )
    env_file = tmp_path / "ops.env"
    env_file.write_text(f"OPS_MAIN_APP_DIR={main_app}\n")

    s = load_settings(env_file=env_file, environ={})

    assert s.main_app_dir == main_app
    assert s.llm_base_url == "http://gw:4000/v1"
    assert s.llm_api_key == "sk-testkey123"
    assert s.llm_model == "deepseek"
    assert s.main_health_url == "http://127.0.0.1:8000/health"
    assert s.db_host == "10.0.0.1"
    assert s.db_port == 3307
    assert len(s.bank_api_urls) == 4
    assert s.bank_api_token == "tok"
    assert s.inspect_interval_minutes == 30
    assert s.evidence_token_budget == 12000


def test_ops_env_overrides_main_app(tmp_path):
    main_app = tmp_path / "backend"
    main_app.mkdir()
    (main_app / ".env").write_text("LLM_MODEL=deepseek\n")
    env_file = tmp_path / "ops.env"
    env_file.write_text(
        f"OPS_MAIN_APP_DIR={main_app}\n"
        "OPS_LLM_MODEL=qwen\n"
        "OPS_TOKEN=abc\n"
        "OPS_INSPECT_INTERVAL_MINUTES=5\n"
    )

    s = load_settings(env_file=env_file, environ={})

    assert s.llm_model == "qwen"
    assert s.ops_token == "abc"
    assert s.inspect_interval_minutes == 5


def test_ops_main_pid_file_override(tmp_path):
    main_app = tmp_path / "backend"
    main_app.mkdir()
    (main_app / ".env").write_text("PORT=8000\n")
    env_file = tmp_path / "ops.env"
    env_file.write_text(
        f"OPS_MAIN_APP_DIR={main_app}\n"
        "OPS_MAIN_PID_FILE=/custom/app.pid\n"
    )

    s = load_settings(env_file=env_file, environ={})

    assert s.main_pid_file == Path("/custom/app.pid")


def test_sqlite_mode_when_no_db_host(tmp_path):
    main_app = tmp_path / "backend"
    main_app.mkdir()
    (main_app / ".env").write_text("PORT=9111\n")
    env_file = tmp_path / "ops.env"
    env_file.write_text(f"OPS_MAIN_APP_DIR={main_app}\n")

    s = load_settings(env_file=env_file, environ={})

    assert s.db_host == ""
    assert s.main_health_url == "http://127.0.0.1:9111/health"
