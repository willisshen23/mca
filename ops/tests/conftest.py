from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import Settings  # noqa: E402


@pytest.fixture
def settings(tmp_path) -> Settings:
    main_app = tmp_path / "backend"
    (main_app / "data" / "logs").mkdir(parents=True)
    (main_app / "data" / "run").mkdir(parents=True)
    return Settings(
        main_app_dir=main_app,
        main_health_url="http://127.0.0.1:8000/health",
        main_pid_file=main_app / "data" / "run" / "activity-analysis-assistant.pid",
        log_dir=main_app / "data" / "logs",
        ops_db_path=tmp_path / "ops" / "ops.db",
        seed_runbook_dir=tmp_path / "seed",
    )
