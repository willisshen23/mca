# ops-assistant 运维助手实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建设独立的只读 Web 运维服务 ops-assistant：规则引擎定时巡检（红黄绿）+ 预编排诊断流水线（采集证据 + 内网 LLM 单次分析 + 可追问）+ 页面可编辑的 runbook 知识库。

**Architecture:** 独立 FastAPI 进程（默认 :9100），源码位于仓库根目录 `ops/`，复用主应用 venv（所有依赖已在离线 wheel 中）。巡检 = 采集器（只读探针）→ YAML 规则判定 → 快照入 SQLite；诊断 = 剧本选定采集器组合 → 证据包（脱敏 + token 截断）+ runbook → 单次 LLM 调用 → 结构化结论；LLM 不可用时降级为规则原文 + runbook 全文。

**Tech Stack:** Python 3.12 / FastAPI / Uvicorn / httpx / PyYAML / PyMySQL / sqlite3（标准库）/ pytest；前端为无构建的静态单页（vanilla HTML/JS）。

**规格文档：** `docs/superpowers/specs/2026-08-06-ops-assistant-design.md`（已批准）

## Global Constraints

- **只读红线**：禁止对主应用与系统做任何写操作（不删文件、不执行重启、数据库只读探测）；ops 只写自己的 SQLite（`ops/data/ops.db`）。
- **依赖红线**：只允许使用主应用 `backend/requirements.txt` 已有的依赖（fastapi、uvicorn、httpx、pyyaml、pymysql、python-dotenv 均已在 `offline-bundle/wheels/` 中；**禁止引入 APScheduler**——离线 wheel 无此包，定时用 asyncio 后台循环）。
- **Python**：开发与运行均使用 `backend/venv/bin/python`（生产为便携 Python 3.12 创建的同一 venv）。
- **测试命令**：一律在 `ops/` 目录下执行 `../backend/venv/bin/python -m pytest tests/<file> -v`。
- **时间**：所有入库时间戳用应用侧 UTC（`datetime.now(timezone.utc).isoformat()`），不用数据库服务器时钟。
- **脱敏**：LLM key、数据库口令、银行 token 不出现在证据包、页面与日志中。
- **提交**：每个任务结束按步骤提交，提交信息用中文短句。
- **目录**：源码 `ops/src/`，测试 `ops/tests/`，页面 `ops/web/static/`，出厂 runbook `ops/runbooks/seed/`。

## 文件结构

```
ops/
  pytest.ini                  # testpaths=tests
  requirements.txt            # 信息性清单（依赖由 backend venv 提供）
  .env.example                # OPS_* 配置模板
  README.md                   # 值班人员使用说明
  server.sh                   # start/stop/status/logs（复用 backend venv）
  src/
    __init__.py
    config.py                 # Settings + load_settings（OPS_* 覆盖，主应用 .env 兜底）
    storage.py                # OpsDB：snapshots / runbooks / diagnoses 三表
    inspection.py             # run_inspection + scheduler_loop
    main.py                   # create_app + 路由 + auth + 静态挂载 + lifespan
    collectors/
      __init__.py             # COLLECTORS 注册表
      base.py                 # Sample + run_collector（超时/异常兜底）
      process.py              # pid 存活 + /health 探测
      logs.py                 # 日志窗口统计 + 模式聚类 + 片段提取
      system.py               # 磁盘/内存/负载
      database.py             # MySQL 探测 / SQLite 文件检查
      llm_gateway.py          # 最小 chat 调用探测
      bank_api.py             # 银行接口探测
    rules/
      __init__.py
      engine.py               # Rule/CheckResult + load_rules + evaluate
      builtins.py             # JUDGES 判定函数
      rules.yaml              # 7 条内置规则
    diagnosis/
      __init__.py
      evidence.py             # 脱敏/组装/token 截断
      llm.py                  # chat() OpenAI 兼容单次调用
      prompts.py              # SYSTEM_PROMPT + render_diagnosis_messages
      pipeline.py             # Playbook/PLAYBOOKS + run_diagnosis + followup
  web/static/index.html       # 单页仪表盘（无构建）
  runbooks/seed/*.md          # 出厂 runbook
  tests/
    conftest.py               # sys.path 注入 + 公共 fixture
    test_config.py
    test_storage.py
    test_collectors_process.py
    test_collectors_logs.py
    test_collectors_system_db.py
    test_collectors_llm_bank.py
    test_rules_engine.py
    test_inspection.py
    test_evidence.py
    test_llm_prompts.py
    test_diagnosis_pipeline.py
    test_api.py
    test_acceptance.py
```

## 关键接口一览（跨任务一致性基准）

```python
# src/config.py
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

def load_settings(env_file=None, environ=None) -> Settings

# src/collectors/base.py
@dataclass
class Sample:
    collector: str
    ok: bool
    metrics: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0

async def run_collector(name, fn, settings, timeout_s=None) -> Sample

# src/collectors/__init__.py
COLLECTORS: dict[str, Callable[[Settings], Awaitable[Sample]]]
# keys: "process" "logs" "system" "database" "llm_gateway" "bank_api"

# src/rules/engine.py
@dataclass
class Rule:
    id: str
    title: str
    collector: str
    judge: str
    params: dict = field(default_factory=dict)

@dataclass
class CheckResult:
    id: str
    title: str
    level: str      # "green" | "yellow" | "red" | "gray"
    message: str

def load_rules(path) -> list[Rule]
def evaluate(samples: dict[str, Sample], rules: list[Rule]) -> list[CheckResult]

# src/rules/builtins.py
JUDGES: dict[str, Callable[[Sample, dict], tuple[str, str] | None]]
# 返回 (level, message) 表示命中异常；None 表示正常

# src/storage.py
class OpsDB:
    def __init__(self, path): ...
    def init(self) -> None: ...
    def save_snapshot(self, overall: str, payload: str) -> int: ...
    def latest_snapshot(self) -> dict | None: ...   # {"id","created_at","overall","payload"(已解析dict)}
    def list_snapshots(self, limit: int = 50) -> list[dict]: ...
    def purge_snapshots(self, days: int) -> None: ...
    def upsert_runbook(self, slug: str, title: str, category: str, body: str) -> None: ...
    def list_runbooks(self) -> list[dict]: ...
    def get_runbook(self, slug: str) -> dict | None: ...
    def get_runbook_by_category(self, category: str) -> dict | None: ...
    def seed_runbooks(self, seed_dir) -> int: ...     # INSERT OR IGNORE，返回导入条数
    def save_diagnosis(self, check_id, playbook, conclusion, transcript, degraded, error) -> int: ...
    def get_diagnosis(self, diagnosis_id: int) -> dict | None: ...
    def append_message(self, diagnosis_id: int, role: str, content: str) -> None: ...

# src/inspection.py
async def run_inspection(settings, db, rules, collectors=None) -> dict
async def scheduler_loop(settings, db, rules, stop_event) -> None

# src/diagnosis/evidence.py
def mask_secrets(text: str) -> str
def build_evidence(check: dict, samples: dict[str, Sample], settings) -> dict
def estimate_tokens(evidence: dict) -> int
def truncate_evidence(evidence: dict, budget_tokens: int) -> dict

# src/diagnosis/llm.py
async def chat(settings, messages: list[dict], transport=None) -> str

# src/diagnosis/prompts.py
SYSTEM_PROMPT: str
def render_diagnosis_messages(check: dict, evidence: dict, runbook_body: str) -> list[dict]

# src/diagnosis/pipeline.py
@dataclass
class Playbook:
    check_id: str
    title: str
    collectors: tuple
    runbook_category: str

PLAYBOOKS: dict[str, Playbook]
DEFAULT_PLAYBOOK: Playbook
def parse_conclusion(text: str) -> dict
async def run_diagnosis(db, settings, check_id, *, chat_fn=None, collectors=None) -> dict
async def followup(db, settings, diagnosis_id, question, *, chat_fn=None) -> dict

# src/main.py
def create_app(settings=None, db=None) -> FastAPI
app = create_app()   # 模块级，供 uvicorn src.main:app
```

---

### Task 1: 项目骨架与配置加载

**Files:**
- Create: `ops/pytest.ini`, `ops/requirements.txt`, `ops/.env.example`, `ops/src/__init__.py`, `ops/src/config.py`, `ops/tests/__init__.py`, `ops/tests/conftest.py`, `ops/tests/test_config.py`

**Interfaces:**
- Produces: `Settings` dataclass 与 `load_settings(env_file=None, environ=None) -> Settings`（签名与字段见"关键接口一览"）。后续所有任务都 import `from src.config import Settings, load_settings`。

- [ ] **Step 1: 创建骨架文件**

`ops/pytest.ini`：

```ini
[pytest]
testpaths = tests
```

`ops/requirements.txt`（信息性清单，实际由 backend venv 提供，不单独安装）：

```text
# ops-assistant 依赖均由主应用 backend venv 提供（离线 wheel 已含），此文件仅作说明。
fastapi
uvicorn
httpx
pyyaml
pymysql
python-dotenv
```

`ops/.env.example`：

```bash
# ops-assistant 配置（全部可选；未设置时自动从主应用 backend/.env 推断）
OPS_PORT=9100
OPS_TOKEN=                      # 页面访问令牌；留空则不启用令牌校验（仅限内网调试）
OPS_MAIN_APP_DIR=               # 主应用目录，默认 ../backend
# OPS_LLM_BASE_URL=             # 默认取主应用 LLM_BASE_URL
# OPS_LLM_API_KEY=              # 默认取主应用 LLM_API_KEY
# OPS_LLM_MODEL=                # 默认取主应用 LLM_MODEL
OPS_INSPECT_INTERVAL_MINUTES=30
OPS_EVIDENCE_TOKEN_BUDGET=12000
OPS_LOG_WINDOW_HOURS=6
```

`ops/src/__init__.py`、`ops/tests/__init__.py`：空文件。

`ops/tests/conftest.py`：

```python
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
```

- [ ] **Step 2: 写失败测试** `ops/tests/test_config.py`

```python
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


def test_sqlite_mode_when_no_db_host(tmp_path):
    main_app = tmp_path / "backend"
    main_app.mkdir()
    (main_app / ".env").write_text("PORT=9111\n")
    env_file = tmp_path / "ops.env"
    env_file.write_text(f"OPS_MAIN_APP_DIR={main_app}\n")

    s = load_settings(env_file=env_file, environ={})

    assert s.db_host == ""
    assert s.main_health_url == "http://127.0.0.1:9111/health"
```

- [ ] **Step 3: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.config'` 或 import 错误）

- [ ] **Step 4: 实现** `ops/src/config.py`

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

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
        main_pid_file=main_app_dir / "data" / "run" / "activity-analysis-assistant.pid",
        log_dir=Path(ops_get("OPS_LOG_DIR") or (main_app_dir / "data" / "logs")),
        ops_db_path=Path(ops_get("OPS_DB_PATH") or (_OPS_DIR / "data" / "ops.db")),
        seed_runbook_dir=Path(ops_get("OPS_SEED_RUNBOOK_DIR") or (_OPS_DIR / "runbooks" / "seed")),
        log_window_hours=int(ops_get("OPS_LOG_WINDOW_HOURS", "6")),
        llm_base_url=ops_get("OPS_LLM_BASE_URL", main_get("LLM_BASE_URL")),
        llm_api_key=ops_get("OPS_LLM_API_KEY", main_get("LLM_API_KEY")),
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
```

- [ ] **Step 5: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add ops/
git commit -m "新增 ops-assistant 骨架与配置加载"
```

---

### Task 2: 存储层 OpsDB

**Files:**
- Create: `ops/src/storage.py`, `ops/tests/test_storage.py`

**Interfaces:**
- Consumes: Task 1 的 `settings` fixture（用到 `ops_db_path`、`seed_runbook_dir`）。
- Produces: `OpsDB` 类，方法签名见"关键接口一览"。`latest_snapshot()` 返回的 dict 中 `payload` 为**已解析的 dict**；`get_runbook*` 返回 `{"slug","title","category","body","updated_at"}`；`get_diagnosis` 返回 `{"id","created_at","check_id","playbook","conclusion","transcript","degraded","error"}`（conclusion/transcript 为 JSON 字符串，由调用方解析）。

- [ ] **Step 1: 写失败测试** `ops/tests/test_storage.py`

```python
from __future__ import annotations

import json

from src.storage import OpsDB


def test_snapshot_roundtrip_and_latest(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    sid1 = db.save_snapshot("green", json.dumps({"overall": "green", "checks": []}))
    sid2 = db.save_snapshot("red", json.dumps({"overall": "red", "checks": [{"id": "x"}]}))
    assert sid2 > sid1

    latest = db.latest_snapshot()
    assert latest["overall"] == "red"
    assert latest["payload"]["checks"] == [{"id": "x"}]
    assert len(db.list_snapshots()) == 2


def test_purge_snapshots_keeps_recent(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    db.save_snapshot("green", "{}")
    db.purge_snapshots(days=7)
    assert len(db.list_snapshots()) == 1
    db.purge_snapshots(days=0)
    assert len(db.list_snapshots()) == 1  # days=0 按"刚写入的不删"处理：仅删早于 cutoff 的
    # 强制清理验证：直接删全部
    db._conn.execute("DELETE FROM snapshots")
    assert db.latest_snapshot() is None


def test_runbook_crud_and_category_lookup(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    db.upsert_runbook("llm-timeout", "LLM 超时", "llm-timeout", "正文v1")
    db.upsert_runbook("llm-timeout", "LLM 超时", "llm-timeout", "正文v2")

    rb = db.get_runbook("llm-timeout")
    assert rb["body"] == "正文v2"
    assert db.get_runbook_by_category("llm-timeout")["slug"] == "llm-timeout"
    assert db.get_runbook_by_category("nonexist") is None
    assert len(db.list_runbooks()) == 1


def test_seed_runbooks_only_imports_once(settings, tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "disk-full.md").write_text("# 磁盘满\n\n清理日志。\n")
    db = OpsDB(settings.ops_db_path)
    db.init()

    assert db.seed_runbooks(seed) == 1
    db.upsert_runbook("disk-full", "磁盘满(改)", "disk-full", "用户改过的正文")
    assert db.seed_runbooks(seed) == 0  # 不覆盖用户编辑
    assert db.get_runbook("disk-full")["body"] == "用户改过的正文"


def test_diagnosis_save_and_append(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    did = db.save_diagnosis("llm-latency", "LLM 延迟诊断", '{"causes":[]}',
                            '[{"role":"user","content":"q"}]', False, None)
    db.append_message(did, "assistant", "回答")

    diag = db.get_diagnosis(did)
    assert diag["check_id"] == "llm-latency"
    transcript = json.loads(diag["transcript"])
    assert transcript[-1] == {"role": "assistant", "content": "回答"}
    assert db.get_diagnosis(9999) is None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_storage.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.storage'`）

- [ ] **Step 3: 实现** `ops/src/storage.py`

```python
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    overall TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runbooks(
    slug TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    body TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS diagnoses(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    check_id TEXT NOT NULL,
    playbook TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    transcript TEXT NOT NULL,
    degraded INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class OpsDB:
    """ops-assistant 自有 SQLite（巡检快照 / runbook / 诊断记录）。"""

    def __init__(self, path):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ---- snapshots ----

    def save_snapshot(self, overall: str, payload: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO snapshots(created_at, overall, payload) VALUES(?,?,?)",
                (_utcnow(), overall, payload),
            )
            self._conn.commit()
            return cur.lastrowid

    def _row_to_snapshot(self, row) -> dict:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "overall": row["overall"],
            "payload": json.loads(row["payload"]),
        }

    def latest_snapshot(self) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def list_snapshots(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def purge_snapshots(self, days: int) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            self._conn.execute("DELETE FROM snapshots WHERE created_at < ?", (cutoff,))
            self._conn.commit()

    # ---- runbooks ----

    def upsert_runbook(self, slug: str, title: str, category: str, body: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO runbooks(slug,title,category,body,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(slug) DO UPDATE SET title=excluded.title, "
                "category=excluded.category, body=excluded.body, updated_at=excluded.updated_at",
                (slug, title, category, body, _utcnow()),
            )
            self._conn.commit()

    def list_runbooks(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT slug,title,category,updated_at FROM runbooks ORDER BY slug"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_runbook(self, slug: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runbooks WHERE slug=?", (slug,)
            ).fetchone()
        return dict(row) if row else None

    def get_runbook_by_category(self, category: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runbooks WHERE category=? ORDER BY slug LIMIT 1", (category,)
            ).fetchone()
        return dict(row) if row else None

    def seed_runbooks(self, seed_dir) -> int:
        seed_dir = Path(seed_dir)
        if not seed_dir.is_dir():
            return 0
        imported = 0
        for md in sorted(seed_dir.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            title = text.splitlines()[0].lstrip("# ").strip() if text.strip() else md.stem
            with self._lock:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO runbooks(slug,title,category,body,updated_at) "
                    "VALUES(?,?,?,?,?)",
                    (md.stem, title, md.stem, text, _utcnow()),
                )
                self._conn.commit()
            imported += cur.rowcount
        return imported

    # ---- diagnoses ----

    def save_diagnosis(self, check_id, playbook, conclusion, transcript, degraded, error) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO diagnoses(created_at,check_id,playbook,conclusion,transcript,"
                "degraded,error) VALUES(?,?,?,?,?,?,?)",
                (_utcnow(), check_id, playbook, conclusion, transcript, int(degraded), error),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_diagnosis(self, diagnosis_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM diagnoses WHERE id=?", (diagnosis_id,)
            ).fetchone()
        return dict(row) if row else None

    def append_message(self, diagnosis_id: int, role: str, content: str) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT transcript FROM diagnoses WHERE id=?", (diagnosis_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"diagnosis {diagnosis_id} 不存在")
            transcript = json.loads(row["transcript"])
            transcript.append({"role": role, "content": content})
            self._conn.execute(
                "UPDATE diagnoses SET transcript=? WHERE id=?",
                (json.dumps(transcript, ensure_ascii=False), diagnosis_id),
            )
            self._conn.commit()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_storage.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/storage.py ops/tests/test_storage.py
git commit -m "新增 ops 存储层（快照/runbook/诊断记录）"
```

---

### Task 3: 采集器基类 + process 采集器

**Files:**
- Create: `ops/src/collectors/__init__.py`（暂为空，Task 6 填注册表）, `ops/src/collectors/base.py`, `ops/src/collectors/process.py`, `ops/tests/test_collectors_process.py`

**Interfaces:**
- Produces: `Sample`、`run_collector`（签名见接口一览）；`process.collect(settings) -> Sample`，metrics 为 `{"pid": int|None, "alive": bool, "health_ok": bool, "health_status": int|None, "health_latency_ms": int|None}`。
- 关键约定：`run_collector` 永不抛异常——采集器抛错/超时一律返回 `Sample(ok=False, error=...)`，这是"单个采集器失败不影响整轮巡检"的根基。

- [ ] **Step 1: 写失败测试** `ops/tests/test_collectors_process.py`

```python
from __future__ import annotations

import asyncio

import pytest

from src.collectors import process
from src.collectors.base import Sample, run_collector


def test_run_collector_returns_sample(settings):
    async def ok_fn(s):
        return Sample("demo", True, metrics={"x": 1})

    sample = asyncio.run(run_collector("demo", ok_fn, settings))
    assert sample.ok and sample.metrics == {"x": 1} and sample.duration_ms >= 0


def test_run_collector_catches_exception(settings):
    async def boom(s):
        raise RuntimeError("炸了")

    sample = asyncio.run(run_collector("demo", boom, settings))
    assert sample.ok is False
    assert "炸了" in sample.error


def test_run_collector_timeout(settings):
    settings.collector_timeout_s = 0.05

    async def slow(s):
        await asyncio.sleep(5)

    sample = asyncio.run(run_collector("demo", slow, settings))
    assert sample.ok is False
    assert "TimeoutError" in sample.error


def _patch_health(monkeypatch, ok=True, status=200, latency=12):
    async def fake_probe(url, timeout):
        return ok, status, latency

    monkeypatch.setattr(process, "_probe_health", fake_probe)


def test_process_alive_and_health_ok(settings, monkeypatch):
    settings.main_pid_file.write_text("12345")
    monkeypatch.setattr(process, "_pid_alive", lambda pid: True)
    _patch_health(monkeypatch)

    sample = asyncio.run(process.collect(settings))

    assert sample.ok
    assert sample.metrics == {
        "pid": 12345, "alive": True,
        "health_ok": True, "health_status": 200, "health_latency_ms": 12,
    }


def test_process_missing_pid_file(settings, monkeypatch):
    _patch_health(monkeypatch, ok=False, status=None, latency=None)

    sample = asyncio.run(process.collect(settings))

    assert sample.metrics["pid"] is None
    assert sample.metrics["alive"] is False
    assert sample.metrics["health_ok"] is False
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_collectors_process.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.collectors'`）

- [ ] **Step 3: 实现**

`ops/src/collectors/__init__.py`：空文件（Task 6 填注册表）。

`ops/src/collectors/base.py`：

```python
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class Sample:
    collector: str
    ok: bool
    metrics: dict = field(default_factory=dict)
    evidence: list = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0


async def run_collector(name, fn, settings, timeout_s=None) -> Sample:
    """执行单个采集器：永不抛异常，失败/超时返回 ok=False 的 Sample。"""
    start = time.monotonic()
    try:
        sample = await asyncio.wait_for(
            fn(settings), timeout_s or settings.collector_timeout_s
        )
        sample.collector = name
        sample.duration_ms = int((time.monotonic() - start) * 1000)
        return sample
    except Exception as exc:  # noqa: BLE001 - 兜底是设计意图
        return Sample(
            collector=name,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
```

`ops/src/collectors/process.py`：

```python
from __future__ import annotations

import os
import time

import httpx

from src.collectors.base import Sample


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _probe_health(url: str, timeout: float):
    """返回 (health_ok, status_code|None, latency_ms|None)。"""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
        latency_ms = int((time.monotonic() - start) * 1000)
        return resp.status_code == 200, resp.status_code, latency_ms
    except Exception:  # noqa: BLE001 - 探测失败即"不健康"
        return False, None, None


async def collect(settings) -> Sample:
    pid = None
    try:
        raw = settings.main_pid_file.read_text().strip()
        pid = int(raw) if raw.isdigit() else None
    except OSError:
        pid = None

    alive = _pid_alive(pid) if pid else False
    health_ok, status, latency = await _probe_health(
        settings.main_health_url, settings.collector_timeout_s
    )
    return Sample(
        "process",
        True,
        metrics={
            "pid": pid,
            "alive": alive,
            "health_ok": health_ok,
            "health_status": status,
            "health_latency_ms": latency,
        },
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_collectors_process.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/collectors/ ops/tests/test_collectors_process.py
git commit -m "新增采集器基类与进程/健康检查采集器"
```

---

### Task 4: logs 采集器

**Files:**
- Create: `ops/src/collectors/logs.py`, `ops/tests/test_collectors_logs.py`

**Interfaces:**
- Produces: `logs.collect(settings) -> Sample`，metrics 为 `{"error_count": int, "warn_count": int, "error_count_yesterday": int, "clusters": {label: int}, "files_scanned": int}`；evidence 为错误片段列表（**新的在前**，每条 ≤500 字符）。
- 窗口口径（简化设计，避免逐行解析时间戳）：日志文件按天命名 `app-YYYY-MM-DD.log`——"当前窗口"= 今天的文件（外加无日期的 `app.log`），"昨日同时段"= 昨天日期的文件。单文件只读末尾 5MB。

- [ ] **Step 1: 写失败测试** `ops/tests/test_collectors_logs.py`

```python
from __future__ import annotations

import asyncio
from datetime import date, timedelta

from src.collectors import logs


def _write_logs(settings, today_lines, yesterday_lines):
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    (settings.log_dir / f"app-{today}.log").write_text(today_lines)
    (settings.log_dir / f"app-{yesterday}.log").write_text(yesterday_lines)


def test_counts_and_clusters(settings):
    _write_logs(
        settings,
        today_lines=(
            "2026-08-06 10:00:01 INFO ok\n"
            "2026-08-06 10:00:02 ERROR LLM request timed out after 600s\n"
            "2026-08-06 10:00:03 ERROR LLM request timed out after 600s\n"
            "2026-08-06 10:00:04 WARNING slow query\n"
        ),
        yesterday_lines="2026-08-05 10:00:02 ERROR one error\n",
    )

    sample = asyncio.run(logs.collect(settings))

    m = sample.metrics
    assert m["error_count"] == 2
    assert m["warn_count"] == 1
    assert m["error_count_yesterday"] == 1
    assert m["clusters"]["timeout"] == 2
    assert m["files_scanned"] == 1  # 当前窗口只数今天的文件
    assert len(sample.evidence) == 2
    assert "timed out" in sample.evidence[0]


def test_missing_log_dir_is_not_an_error(settings):
    settings.log_dir = settings.main_app_dir / "no-such-dir"

    sample = asyncio.run(logs.collect(settings))

    assert sample.ok is True
    assert sample.metrics["error_count"] == 0
    assert sample.metrics["files_scanned"] == 0


def test_snippets_newest_first_and_truncated(settings):
    lines = "".join(f"2026-08-06 10:{i:02d}:00 ERROR err-{i} {'x' * 600}\n" for i in range(30))
    _write_logs(settings, today_lines=lines, yesterday_lines="")

    sample = asyncio.run(logs.collect(settings))

    assert "err-29" in sample.evidence[0]           # 最新优先
    assert len(sample.evidence[0]) <= 520           # 截断（500 + 省略标记）
    assert len(sample.evidence) <= 20               # 上限条数
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_collectors_logs.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.collectors.logs'`）

- [ ] **Step 3: 实现** `ops/src/collectors/logs.py`

```python
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta

from src.collectors.base import Sample

_ERROR_RE = re.compile(r"\bERROR\b")
_WARN_RE = re.compile(r"\bWARNING\b")

_PATTERNS = [
    (re.compile(r"timed?\s*out|timeout", re.I), "timeout"),
    (re.compile(r"connection\s*(refused|reset|error)|connect.*failed", re.I), "connection"),
    (re.compile(r"\b5\d{2}\b.*(bank|接口|api)|status[_ ]?code[=: ]?5\d{2}", re.I), "http_5xx"),
    (re.compile(r"out of memory|MemoryError", re.I), "memory"),
    (re.compile(r"unauthorized|forbidden|\b40[13]\b|api[_ ]?key", re.I), "auth"),
]

_TAIL_BYTES = 5 * 1024 * 1024
_MAX_SNIPPETS = 20
_SNIPPET_CHARS = 500


def _read_tail(path) -> str:
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > _TAIL_BYTES:
            f.seek(-_TAIL_BYTES, 2)
        return f.read().decode("utf-8", errors="replace")


def _scan_file(path) -> dict:
    errors = warns = 0
    clusters: dict[str, int] = {}
    snippets: list[str] = []
    for line in _read_tail(path).splitlines():
        if _ERROR_RE.search(line):
            errors += 1
            for pattern, label in _PATTERNS:
                if pattern.search(line):
                    clusters[label] = clusters.get(label, 0) + 1
                    break
            snippet = line.strip()
            if len(snippet) > _SNIPPET_CHARS:
                snippet = snippet[:_SNIPPET_CHARS] + " …(截断)"
            snippets.append(snippet)
        elif _WARN_RE.search(line):
            warns += 1
    snippets.reverse()  # 最新优先
    return {
        "errors": errors,
        "warns": warns,
        "clusters": clusters,
        "snippets": snippets[:_MAX_SNIPPETS],
    }


def _count_errors(path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in _read_tail(path).splitlines() if _ERROR_RE.search(line))


def _scan_sync(settings) -> Sample:
    log_dir = settings.log_dir
    if not log_dir.is_dir():
        return Sample("logs", True, metrics={
            "error_count": 0, "warn_count": 0, "error_count_yesterday": 0,
            "clusters": {}, "files_scanned": 0,
        })

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    current_files = []
    for name in (f"app-{today}.log", "app.log"):
        p = log_dir / name
        if p.exists():
            current_files.append(p)

    errors = warns = 0
    clusters: dict[str, int] = {}
    snippets: list[str] = []
    for path in current_files:
        result = _scan_file(path)
        errors += result["errors"]
        warns += result["warns"]
        for label, count in result["clusters"].items():
            clusters[label] = clusters.get(label, 0) + count
        snippets.extend(result["snippets"])

    yesterday_errors = _count_errors(log_dir / f"app-{yesterday}.log")

    return Sample(
        "logs",
        True,
        metrics={
            "error_count": errors,
            "warn_count": warns,
            "error_count_yesterday": yesterday_errors,
            "clusters": clusters,
            "files_scanned": len(current_files),
        },
        evidence=snippets[:_MAX_SNIPPETS],
    )


async def collect(settings) -> Sample:
    return await asyncio.to_thread(_scan_sync, settings)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_collectors_logs.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/collectors/logs.py ops/tests/test_collectors_logs.py
git commit -m "新增日志采集器（窗口统计/模式聚类/片段提取）"
```

---

### Task 5: system + database 采集器

**Files:**
- Create: `ops/src/collectors/system.py`, `ops/src/collectors/database.py`, `ops/tests/test_collectors_system_db.py`

**Interfaces:**
- Produces:
  - `system.collect(settings)` metrics：`{"disk_pct": float, "disk_path": str, "mem_pct": float|None, "load1": float|None}`（disk_pct 取主应用目录与日志目录所在分区的较大值）。
  - `database.collect(settings)` metrics：MySQL 模式 `{"mode":"mysql","reachable":bool,"latency_ms":int|None,"error":str|None}`；SQLite 模式 `{"mode":"sqlite","reachable":bool,"files":[{"path":str,"size_mb":float}]}`。

- [ ] **Step 1: 写失败测试** `ops/tests/test_collectors_system_db.py`

```python
from __future__ import annotations

import asyncio
import shutil
from collections import namedtuple

from src.collectors import database, system

_Usage = namedtuple("usage", "total used free")


def test_system_disk_pct_takes_max(settings, monkeypatch):
    def fake_usage(path):
        if "logs" in str(path):
            return _Usage(100, 90, 10)   # 90%
        return _Usage(100, 50, 50)       # 50%

    monkeypatch.setattr(shutil, "disk_usage", fake_usage)
    monkeypatch.setattr(system, "_read_mem_pct", lambda: 42.0)

    sample = asyncio.run(system.collect(settings))

    assert sample.metrics["disk_pct"] == 90.0
    assert sample.metrics["mem_pct"] == 42.0


def test_database_sqlite_mode(settings):
    db_file = settings.main_app_dir / "data" / "skills.db"
    db_file.write_bytes(b"x" * 1024)

    sample = asyncio.run(database.collect(settings))

    assert sample.metrics["mode"] == "sqlite"
    assert sample.metrics["reachable"] is True
    assert sample.metrics["files"][0]["path"].endswith("skills.db")


def test_database_sqlite_missing_dir(settings):
    settings.main_app_dir = settings.main_app_dir / "gone"

    sample = asyncio.run(database.collect(settings))

    assert sample.metrics["mode"] == "sqlite"
    assert sample.metrics["reachable"] is False


def test_database_mysql_reachable(settings, monkeypatch):
    settings.db_host = "10.0.0.1"

    class _Cursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql): assert sql == "SELECT 1"

    class _Conn:
        def cursor(self): return _Cursor()
        def close(self): pass

    monkeypatch.setattr(database, "_connect_mysql", lambda s: _Conn())

    sample = asyncio.run(database.collect(settings))

    assert sample.metrics["mode"] == "mysql"
    assert sample.metrics["reachable"] is True
    assert sample.metrics["latency_ms"] is not None


def test_database_mysql_refused(settings, monkeypatch):
    settings.db_host = "10.0.0.1"

    def refuse(s):
        raise ConnectionError("refused")

    monkeypatch.setattr(database, "_connect_mysql", refuse)

    sample = asyncio.run(database.collect(settings))

    assert sample.metrics["reachable"] is False
    assert "refused" in sample.metrics["error"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_collectors_system_db.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`ops/src/collectors/system.py`：

```python
from __future__ import annotations

import asyncio
import os
import shutil

from src.collectors.base import Sample


def _read_mem_pct() -> float | None:
    """读 /proc/meminfo；非 Linux（如开发机 macOS）返回 None。"""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = int(rest.strip().split()[0])
        total, available = info["MemTotal"], info["MemAvailable"]
        return round((1 - available / total) * 100, 1)
    except (OSError, KeyError, ZeroDivisionError):
        return None


def _scan_sync(settings) -> Sample:
    pcts = []
    worst_path = ""
    for path in {settings.main_app_dir.resolve(), settings.log_dir.resolve()}:
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        pct = round(usage.used / usage.total * 100, 1)
        pcts.append(pct)
        if pct == max(pcts):
            worst_path = str(path)
    try:
        load1 = round(os.getloadavg()[0], 2)
    except OSError:
        load1 = None
    return Sample("system", True, metrics={
        "disk_pct": max(pcts) if pcts else None,
        "disk_path": worst_path,
        "mem_pct": _read_mem_pct(),
        "load1": load1,
    })


async def collect(settings) -> Sample:
    return await asyncio.to_thread(_scan_sync, settings)
```

`ops/src/collectors/database.py`：

```python
from __future__ import annotations

import asyncio
import time

from src.collectors.base import Sample


def _connect_mysql(settings):
    import pymysql

    return pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name or None,
        connect_timeout=int(settings.collector_timeout_s),
        read_timeout=int(settings.collector_timeout_s),
    )


def _probe_mysql(settings) -> Sample:
    start = time.monotonic()
    try:
        conn = _connect_mysql(settings)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        finally:
            conn.close()
        return Sample("database", True, metrics={
            "mode": "mysql", "reachable": True,
            "latency_ms": int((time.monotonic() - start) * 1000), "error": None,
        })
    except Exception as exc:  # noqa: BLE001 - 不可达是正常探测结果
        return Sample("database", True, metrics={
            "mode": "mysql", "reachable": False, "latency_ms": None,
            "error": f"{type(exc).__name__}: {exc}",
        })


def _probe_sqlite(settings) -> Sample:
    data_dir = settings.main_app_dir / "data"
    files = []
    if data_dir.is_dir():
        for db in sorted(data_dir.glob("*.db")):
            try:
                size_mb = round(db.stat().st_size / 1024 / 1024, 1)
                with db.open("rb") as f:
                    f.read(1)
                files.append({"path": str(db), "size_mb": size_mb})
            except OSError:
                pass
    return Sample("database", True, metrics={
        "mode": "sqlite", "reachable": bool(files), "files": files,
    })


async def collect(settings) -> Sample:
    if settings.db_host:
        return await asyncio.to_thread(_probe_mysql, settings)
    return await asyncio.to_thread(_probe_sqlite, settings)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_collectors_system_db.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/collectors/system.py ops/src/collectors/database.py ops/tests/test_collectors_system_db.py
git commit -m "新增系统与数据库采集器"
```

---

### Task 6: llm_gateway + bank_api 采集器 + COLLECTORS 注册表

**Files:**
- Create: `ops/src/collectors/llm_gateway.py`, `ops/src/collectors/bank_api.py`, `ops/tests/test_collectors_llm_bank.py`
- Modify: `ops/src/collectors/__init__.py`（填注册表）

**Interfaces:**
- Produces:
  - `llm_gateway.collect(settings)` metrics：`{"configured": bool, "reachable": bool, "latency_s": float|None, "error": str|None}`。探测用最小 chat 调用（`max_tokens=1`）。
  - `bank_api.collect(settings)` metrics：`{"endpoints": [{"url": str, "reachable": bool, "status": int|None, "latency_ms": int|None}]}`。
  - `COLLECTORS`：`{"process":..., "logs":..., "system":..., "database":..., "llm_gateway":..., "bank_api":...}`。
- 两个 HTTP 采集器的内部探测函数都接受 `transport=None` 参数，测试用 `httpx.MockTransport` 注入。

- [ ] **Step 1: 写失败测试** `ops/tests/test_collectors_llm_bank.py`

```python
from __future__ import annotations

import asyncio

import httpx

from src.collectors import COLLECTORS, bank_api, llm_gateway


def _settings_with_llm(settings):
    settings.llm_base_url = "http://gw:4000/v1"
    settings.llm_api_key = "sk-x"
    settings.llm_model = "deepseek"
    return settings


def test_llm_gateway_ok(settings):
    _settings_with_llm(settings)

    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer sk-x"
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
        })

    sample = asyncio.run(llm_gateway._probe(settings, transport=httpx.MockTransport(handler)))

    assert sample.metrics["reachable"] is True
    assert sample.metrics["latency_s"] is not None


def test_llm_gateway_down(settings):
    _settings_with_llm(settings)

    def handler(request):
        raise httpx.ConnectError("refused")

    sample = asyncio.run(llm_gateway._probe(settings, transport=httpx.MockTransport(handler)))

    assert sample.metrics["reachable"] is False
    assert "refused" in sample.metrics["error"]


def test_llm_gateway_unconfigured(settings):
    sample = asyncio.run(llm_gateway.collect(settings))

    assert sample.metrics["configured"] is False
    assert sample.metrics["reachable"] is False


def test_bank_api_mixed(settings):
    settings.bank_api_urls = ["http://bank/a", "http://bank/b"]
    settings.bank_api_token = "tok"

    def handler(request):
        if request.url.path == "/a":
            return httpx.Response(200, json={})
        raise httpx.ConnectError("refused")

    transport = httpx.MockTransport(handler)
    sample = asyncio.run(bank_api._probe_all(settings, transport=transport))

    eps = sample.metrics["endpoints"]
    assert eps[0]["reachable"] is True and eps[0]["status"] == 200
    assert eps[1]["reachable"] is False


def test_collectors_registry_complete():
    assert set(COLLECTORS) == {
        "process", "logs", "system", "database", "llm_gateway", "bank_api",
    }
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_collectors_llm_bank.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`ops/src/collectors/llm_gateway.py`：

```python
from __future__ import annotations

import time

import httpx

from src.collectors.base import Sample


async def _probe(settings, transport=None) -> Sample:
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    headers = {}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(
            timeout=settings.collector_timeout_s, transport=transport
        ) as client:
            resp = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
        latency = round(time.monotonic() - start, 2)
        reachable = resp.status_code == 200
        return Sample("llm_gateway", True, metrics={
            "configured": True, "reachable": reachable, "latency_s": latency,
            "error": None if reachable else f"HTTP {resp.status_code}",
        })
    except Exception as exc:  # noqa: BLE001 - 探测失败即结果
        return Sample("llm_gateway", True, metrics={
            "configured": True, "reachable": False, "latency_s": None,
            "error": f"{type(exc).__name__}: {exc}",
        })


async def collect(settings) -> Sample:
    if not settings.llm_base_url:
        return Sample("llm_gateway", True, metrics={
            "configured": False, "reachable": False, "latency_s": None,
            "error": "未配置 LLM 网关",
        })
    return await _probe(settings)
```

`ops/src/collectors/bank_api.py`：

```python
from __future__ import annotations

import asyncio
import time

import httpx

from src.collectors.base import Sample


async def _probe_one(url: str, token: str, timeout: float, transport=None) -> dict:
    headers = {"Authorization": token} if token else {}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            resp = await client.post(url, json={}, headers=headers)
        return {
            "url": url, "reachable": True, "status": resp.status_code,
            "latency_ms": int((time.monotonic() - start) * 1000),
        }
    except Exception:  # noqa: BLE001 - 探测失败即结果
        return {"url": url, "reachable": False, "status": None, "latency_ms": None}


async def _probe_all(settings, transport=None) -> Sample:
    endpoints = await asyncio.gather(*(
        _probe_one(url, settings.bank_api_token, settings.collector_timeout_s, transport)
        for url in settings.bank_api_urls
    ))
    return Sample("bank_api", True, metrics={"endpoints": list(endpoints)})


async def collect(settings) -> Sample:
    return await _probe_all(settings)
```

`ops/src/collectors/__init__.py`（替换为空注册表的完整实现）：

```python
from __future__ import annotations

from src.collectors import bank_api, database, llm_gateway, logs, process, system

COLLECTORS = {
    "process": process.collect,
    "logs": logs.collect,
    "system": system.collect,
    "database": database.collect,
    "llm_gateway": llm_gateway.collect,
    "bank_api": bank_api.collect,
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_collectors_llm_bank.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/collectors/ ops/tests/test_collectors_llm_bank.py
git commit -m "新增 LLM 网关与银行接口采集器及注册表"
```

---

### Task 7: 规则引擎 + 内置判定 + rules.yaml

**Files:**
- Create: `ops/src/rules/__init__.py`（空）, `ops/src/rules/engine.py`, `ops/src/rules/builtins.py`, `ops/src/rules/rules.yaml`, `ops/tests/test_rules_engine.py`

**Interfaces:**
- Produces: `Rule`、`CheckResult`、`load_rules(path)`、`evaluate(samples, rules)`、`JUDGES`（签名见接口一览）。
- 约定：judge 返回 `(level, message)` 表示命中异常（level ∈ yellow/red），返回 `None` 表示该规则为绿；采集器失败/缺失 → `gray`，不调用 judge。

- [ ] **Step 1: 写失败测试** `ops/tests/test_rules_engine.py`

```python
from __future__ import annotations

from pathlib import Path

from src.collectors.base import Sample
from src.rules.builtins import JUDGES
from src.rules.engine import Rule, evaluate, load_rules

RULES_YAML = """
- id: process-alive
  title: 主应用进程存活
  collector: process
  judge: process_alive
- id: disk-usage
  title: 磁盘水位
  collector: system
  judge: disk_usage
  params: {warn_pct: 85, red_pct: 95}
"""


def _write_rules(tmp_path) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(RULES_YAML)
    return p


def test_load_rules(tmp_path):
    rules = load_rules(_write_rules(tmp_path))
    assert rules[0].id == "process-alive"
    assert rules[1].params == {"warn_pct": 85, "red_pct": 95}


def test_evaluate_green_when_judge_returns_none(tmp_path):
    rules = load_rules(_write_rules(tmp_path))
    samples = {
        "process": Sample("process", True, metrics={"alive": True}),
        "system": Sample("system", True, metrics={"disk_pct": 50.0}),
    }
    checks = evaluate(samples, rules)
    assert [c.level for c in checks] == ["green", "green"]
    assert checks[0].message == "正常"


def test_evaluate_red_and_yellow(tmp_path):
    rules = load_rules(_write_rules(tmp_path))
    samples = {
        "process": Sample("process", True, metrics={"alive": False, "pid": None}),
        "system": Sample("system", True, metrics={"disk_pct": 88.0}),
    }
    checks = evaluate(samples, rules)
    assert checks[0].level == "red" and "进程" in checks[0].message
    assert checks[1].level == "yellow" and "88" in checks[1].message


def test_evaluate_gray_when_collector_failed(tmp_path):
    rules = load_rules(_write_rules(tmp_path))
    samples = {"process": Sample("process", False, error="TimeoutError: x")}
    checks = evaluate(samples, rules)
    assert checks[0].level == "gray"
    assert "TimeoutError" in checks[0].message
    assert checks[1].level == "gray" and checks[1].message == "采集器未执行"


def test_judge_log_error_spike():
    judge = JUDGES["log_error_spike"]
    params = {"warn_min": 5, "red_min": 20}
    assert judge(Sample("logs", True, metrics={"error_count": 0, "error_count_yesterday": 0}), params) is None
    level, _ = judge(Sample("logs", True, metrics={"error_count": 8, "error_count_yesterday": 2}), params)
    assert level == "yellow"
    level, _ = judge(Sample("logs", True, metrics={"error_count": 30, "error_count_yesterday": 3}), params)
    assert level == "red"


def test_judge_llm_latency():
    judge = JUDGES["llm_latency"]
    params = {"warn_s": 10, "red_s": 30}
    level, msg = judge(Sample("llm_gateway", True, metrics={"reachable": False, "error": "x"}), params)
    assert level == "red"
    level, _ = judge(Sample("llm_gateway", True, metrics={"reachable": True, "latency_s": 45}), params)
    assert level == "red"
    level, _ = judge(Sample("llm_gateway", True, metrics={"reachable": True, "latency_s": 15}), params)
    assert level == "yellow"
    assert judge(Sample("llm_gateway", True, metrics={"reachable": True, "latency_s": 2}), params) is None


def test_builtin_rules_yaml_loads_and_judges_exist():
    rules = load_rules(Path(__file__).resolve().parents[1] / "src" / "rules" / "rules.yaml")
    assert len(rules) == 7
    for rule in rules:
        assert rule.judge in JUDGES, f"{rule.id} 引用了不存在的 judge {rule.judge}"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_rules_engine.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`ops/src/rules/engine.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from src.rules.builtins import JUDGES


@dataclass
class Rule:
    id: str
    title: str
    collector: str
    judge: str
    params: dict = field(default_factory=dict)


@dataclass
class CheckResult:
    id: str
    title: str
    level: str
    message: str


def load_rules(path) -> list[Rule]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    return [
        Rule(
            id=item["id"],
            title=item["title"],
            collector=item["collector"],
            judge=item["judge"],
            params=item.get("params") or {},
        )
        for item in raw
    ]


def evaluate(samples: dict, rules: list[Rule]) -> list[CheckResult]:
    results = []
    for rule in rules:
        sample = samples.get(rule.collector)
        if sample is None:
            results.append(CheckResult(rule.id, rule.title, "gray", "采集器未执行"))
            continue
        if not sample.ok:
            results.append(CheckResult(rule.id, rule.title, "gray", f"采集失败：{sample.error}"))
            continue
        verdict = JUDGES[rule.judge](sample, rule.params)
        if verdict is None:
            results.append(CheckResult(rule.id, rule.title, "green", "正常"))
        else:
            level, message = verdict
            results.append(CheckResult(rule.id, rule.title, level, message))
    return results
```

`ops/src/rules/builtins.py`：

```python
from __future__ import annotations


def process_alive(sample, params):
    if not sample.metrics.get("alive"):
        pid = sample.metrics.get("pid")
        hint = f"pid={pid}" if pid else "pid 文件缺失或为空"
        return ("red", f"主应用进程不存在（{hint}）")
    return None


def health_latency(sample, params):
    m = sample.metrics
    if not m.get("health_ok"):
        status = m.get("health_status")
        return ("red", f"健康检查失败（{'HTTP ' + str(status) if status else '无响应'}）")
    latency = m.get("health_latency_ms") or 0
    if latency >= params.get("red_ms", 10000):
        return ("red", f"健康检查严重超时（{latency}ms）")
    if latency >= params.get("warn_ms", 2000):
        return ("yellow", f"健康检查偏慢（{latency}ms）")
    return None


def log_error_spike(sample, params):
    now = sample.metrics.get("error_count", 0)
    yesterday = sample.metrics.get("error_count_yesterday", 0)
    warn_min = params.get("warn_min", 5)
    red_min = params.get("red_min", 20)
    baseline = max(yesterday, 1)
    if now >= red_min and now > 3 * baseline:
        return ("red", f"错误日志突增：当前窗口 {now} 条，昨日同时段 {yesterday} 条")
    if now >= warn_min and now > baseline:
        return ("yellow", f"错误日志增多：当前窗口 {now} 条，昨日同时段 {yesterday} 条")
    return None


def disk_usage(sample, params):
    pct = sample.metrics.get("disk_pct")
    if pct is None:
        return None
    if pct >= params.get("red_pct", 95):
        return ("red", f"磁盘使用率 {pct}%（{sample.metrics.get('disk_path', '')}）")
    if pct >= params.get("warn_pct", 85):
        return ("yellow", f"磁盘使用率 {pct}%（{sample.metrics.get('disk_path', '')}）")
    return None


def mysql_reachable(sample, params):
    m = sample.metrics
    if m.get("mode") == "mysql" and not m.get("reachable"):
        return ("red", f"MySQL 不可达：{m.get('error') or '未知原因'}")
    if m.get("mode") == "sqlite" and not m.get("reachable"):
        return ("red", "SQLite 数据目录不存在或无可读 .db 文件")
    return None


def llm_latency(sample, params):
    m = sample.metrics
    if not m.get("reachable"):
        return ("red", f"LLM 网关不可达：{m.get('error') or '未配置'}")
    latency = m.get("latency_s") or 0
    if latency >= params.get("red_s", 30):
        return ("red", f"LLM 网关响应严重超时（{latency}s）")
    if latency >= params.get("warn_s", 10):
        return ("yellow", f"LLM 网关响应偏慢（{latency}s）")
    return None


def bank_api(sample, params):
    endpoints = sample.metrics.get("endpoints", [])
    down = [e for e in endpoints if not e.get("reachable")]
    if down:
        urls = "、".join(e["url"] for e in down)
        return ("red", f"{len(down)} 个银行接口不可达：{urls}")
    bad = [e for e in endpoints if (e.get("status") or 0) >= 500]
    if bad:
        urls = "、".join(f"{e['url']}(HTTP {e['status']})" for e in bad)
        return ("yellow", f"银行接口返回 5xx：{urls}")
    return None


JUDGES = {
    "process_alive": process_alive,
    "health_latency": health_latency,
    "log_error_spike": log_error_spike,
    "disk_usage": disk_usage,
    "mysql_reachable": mysql_reachable,
    "llm_latency": llm_latency,
    "bank_api": bank_api,
}
```

`ops/src/rules/rules.yaml`：

```yaml
- id: process-alive
  title: 主应用进程存活
  collector: process
  judge: process_alive
- id: health-timeout
  title: 健康检查响应
  collector: process
  judge: health_latency
  params: {warn_ms: 2000, red_ms: 10000}
- id: log-error-spike
  title: 错误日志突增
  collector: logs
  judge: log_error_spike
  params: {warn_min: 5, red_min: 20}
- id: disk-usage
  title: 磁盘水位
  collector: system
  judge: disk_usage
  params: {warn_pct: 85, red_pct: 95}
- id: mysql-unreachable
  title: 数据库可达性
  collector: database
  judge: mysql_reachable
- id: llm-latency
  title: LLM 网关延迟
  collector: llm_gateway
  judge: llm_latency
  params: {warn_s: 10, red_s: 30}
- id: bank-api
  title: 银行营销接口
  collector: bank_api
  judge: bank_api
```

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_rules_engine.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/rules/ ops/tests/test_rules_engine.py
git commit -m "新增规则引擎与 7 条内置巡检规则"
```

---

### Task 8: 巡检编排与定时循环

**Files:**
- Create: `ops/src/inspection.py`, `ops/tests/test_inspection.py`

**Interfaces:**
- Consumes: `COLLECTORS`、`run_collector`、`evaluate`、`OpsDB.save_snapshot/purge_snapshots`、`Settings.inspect_interval_minutes/snapshot_retention_days`。
- Produces: `run_inspection(settings, db, rules, collectors=None) -> dict`（返回 payload：`{"id","created_at","overall","checks":[...],"samples":{...}}`）；`scheduler_loop(settings, db, rules, stop_event)`。overall 取所有 check 中最严重级别，严重度排序 `green < gray < yellow < red`。

- [ ] **Step 1: 写失败测试** `ops/tests/test_inspection.py`

```python
from __future__ import annotations

import asyncio

from src.collectors.base import Sample
from src.inspection import run_inspection, scheduler_loop
from src.rules.engine import Rule
from src.storage import OpsDB


def _rules():
    return [
        Rule("process-alive", "进程", "process", "process_alive"),
        Rule("disk-usage", "磁盘", "system", "disk_usage", {"warn_pct": 85, "red_pct": 95}),
    ]


def _db(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    return db


def _collectors(process_alive=True, disk_pct=50.0):
    async def process_collect(s):
        return Sample("process", True, metrics={"alive": process_alive})

    async def system_collect(s):
        return Sample("system", True, metrics={"disk_pct": disk_pct})

    return {"process": process_collect, "system": system_collect}


def test_run_inspection_overall_red_and_persisted(settings):
    db = _db(settings)
    payload = asyncio.run(
        run_inspection(settings, db, _rules(), collectors=_collectors(process_alive=False))
    )
    assert payload["overall"] == "red"
    levels = {c["id"]: c["level"] for c in payload["checks"]}
    assert levels == {"process-alive": "red", "disk-usage": "green"}

    latest = db.latest_snapshot()
    assert latest["id"] == payload["id"]
    assert latest["payload"]["overall"] == "red"


def test_run_inspection_gray_beats_green(settings):
    db = _db(settings)

    async def broken(s):
        raise RuntimeError("x")

    collectors = _collectors()
    collectors["system"] = broken
    payload = asyncio.run(run_inspection(settings, db, _rules(), collectors=collectors))
    assert payload["overall"] == "gray"


def test_run_inspection_degrades_when_db_broken(settings):
    """ops SQLite 损坏时：巡检照常返回结果，仅标记 persisted=False（规格 6 降级）。"""
    db = _db(settings)
    db._conn.execute("DROP TABLE snapshots")  # 模拟库损坏

    payload = asyncio.run(
        run_inspection(settings, db, _rules(), collectors=_collectors())
    )
    assert payload["overall"] == "green"
    assert payload["persisted"] is False
    assert payload["id"] is None


def test_scheduler_loop_runs_then_stops(settings):
    db = _db(settings)
    settings.inspect_interval_minutes = 0  # 立即进入下一轮
    stop = asyncio.Event()
    runs = []

    original = run_inspection

    async def counting(settings, db, rules, collectors=None):
        runs.append(1)
        if len(runs) >= 2:
            stop.set()
        return await original(settings, db, rules, collectors=_collectors())

    import src.inspection as insp

    async def _main():
        insp_run = counting
        # scheduler_loop 内部调用模块级 run_inspection，这里直接替换引用
        insp.run_inspection = insp_run
        try:
            await asyncio.wait_for(scheduler_loop(settings, db, _rules(), stop), timeout=5)
        finally:
            insp.run_inspection = original

    asyncio.run(_main())
    assert len(runs) >= 2
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_inspection.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.inspection'`）

- [ ] **Step 3: 实现** `ops/src/inspection.py`

```python
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from src.collectors import COLLECTORS
from src.collectors.base import run_collector
from src.rules.engine import evaluate

logger = logging.getLogger("ops.inspection")

_LEVEL_ORDER = {"green": 0, "gray": 1, "yellow": 2, "red": 3}


async def run_inspection(settings, db, rules, collectors=None) -> dict:
    """执行一轮巡检：并行采集 → 规则判定 → 快照入库 → 返回 payload。"""
    collectors = collectors or COLLECTORS
    samples_list = await asyncio.gather(*(
        run_collector(name, fn, settings) for name, fn in collectors.items()
    ))
    samples = {s.collector: s for s in samples_list}
    checks = evaluate(samples, rules)
    overall = "green"
    for check in checks:
        if _LEVEL_ORDER[check.level] > _LEVEL_ORDER[overall]:
            overall = check.level

    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "checks": [asdict(c) for c in checks],
        "samples": {name: asdict(s) for name, s in samples.items()},
    }
    try:
        snapshot_id = db.save_snapshot(overall, json.dumps(payload, ensure_ascii=False))
        db.purge_snapshots(settings.snapshot_retention_days)
        payload["id"] = snapshot_id
        payload["persisted"] = True
    except Exception:  # noqa: BLE001 - ops 库损坏/磁盘满时降级为仅返回结果
        logger.exception("巡检快照入库失败，本轮结果仅实时展示")
        payload["id"] = None
        payload["persisted"] = False
    return payload


async def scheduler_loop(settings, db, rules, stop_event) -> None:
    """后台定时巡检：启动即跑一轮，之后每 interval 分钟一轮；单轮失败不中断循环。"""
    while not stop_event.is_set():
        try:
            await run_inspection(settings, db, rules)
        except Exception:  # noqa: BLE001 - 巡检失败不杀死调度器
            logger.exception("定时巡检执行失败")
        interval = max(settings.inspect_interval_minutes, 0) * 60
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval or 0.001)
        except asyncio.TimeoutError:
            pass
```

注意：`scheduler_loop` 内部调用的是模块级 `run_inspection`，测试通过替换 `src.inspection.run_inspection` 生效——保持这个引用方式（不要改成 `from ... import` 局部绑定）。

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_inspection.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/inspection.py ops/tests/test_inspection.py
git commit -m "新增巡检编排与 asyncio 定时循环"
```

---

### Task 9: 证据包（脱敏 / 组装 / token 截断）

**Files:**
- Create: `ops/src/diagnosis/__init__.py`（空）, `ops/src/diagnosis/evidence.py`, `ops/tests/test_evidence.py`

**Interfaces:**
- Produces: `mask_secrets(text) -> str`、`build_evidence(check, samples, settings) -> dict`、`estimate_tokens(evidence) -> int`、`truncate_evidence(evidence, budget_tokens) -> dict`。
- 结构约定：`build_evidence` 返回 `{"check": dict, "samples": {name: {"metrics":..., "evidence": [...]}}, "app_config": {...}}`；`app_config` 只含非敏感字段（llm_base_url/llm_model/llm_timeout_s/db_host/db_port/db_name/bank_api_urls），**从字段选择上就不包含 key/口令**，再叠加 `mask_secrets` 兜底。token 估算：2 字符 ≈ 1 token（中英文混合的保守值）。

- [ ] **Step 1: 写失败测试** `ops/tests/test_evidence.py`

```python
from __future__ import annotations

from src.collectors.base import Sample
from src.diagnosis.evidence import (
    build_evidence,
    estimate_tokens,
    mask_secrets,
    truncate_evidence,
)


def test_mask_secrets_masks_keys_and_passwords():
    text = '调用 http://gw/v1 使用 sk-abcdef1234567890，password="SuperSecret123"，正常内容保留'
    masked = mask_secrets(text)
    assert "SuperSecret123" not in masked
    assert "abcdef1234567890" not in masked
    assert "正常内容保留" in masked


def test_build_evidence_excludes_sensitive_config(settings):
    settings.llm_api_key = "sk-should-not-appear"
    settings.db_password = "db-pw"
    settings.bank_api_token = "bank-tok"
    settings.db_host = "10.0.0.1"
    check = {"id": "llm-latency", "title": "LLM 网关延迟", "level": "red", "message": "超时"}
    samples = {"logs": Sample("logs", True, metrics={"error_count": 3}, evidence=["line1"])}

    evidence = build_evidence(check, samples, settings)
    dumped = str(evidence)
    assert "sk-should-not-appear" not in dumped
    assert "db-pw" not in dumped
    assert "bank-tok" not in dumped
    assert evidence["app_config"]["db_host"] == "10.0.0.1"
    assert evidence["samples"]["logs"]["evidence"] == ["line1"]


def test_truncate_evidence_drops_oldest_snippets_first():
    evidence = {
        "check": {"id": "x"},
        "samples": {"logs": {"metrics": {}, "evidence": ["newest", "middle", "oldest" * 100]}},
        "app_config": {},
    }
    budget = estimate_tokens({"check": {"id": "x"}, "samples": {"logs": {"metrics": {}, "evidence": ["newest"]}}, "app_config": {}}) + 10

    out = truncate_evidence(evidence, budget)

    assert out["truncated"] is True
    remaining = out["samples"]["logs"]["evidence"]
    assert "newest" in remaining            # 最新优先保留
    assert estimate_tokens(out) <= budget


def test_estimate_tokens_scales_with_size():
    small = estimate_tokens({"a": "x" * 100})
    big = estimate_tokens({"a": "x" * 1000})
    assert big > small > 0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_evidence.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现** `ops/src/diagnosis/evidence.py`

```python
from __future__ import annotations

import json
import re

_SK_RE = re.compile(r"\bsk-[A-Za-z0-9]{4}[A-Za-z0-9_-]*")
_KV_RE = re.compile(
    r'("(?:[^"]*(?:key|token|password|secret|passwd)[^"]*)"\s*:\s*")[^"]*(")', re.I
)
_PLAIN_KV_RE = re.compile(
    r"\b(password|passwd|token|secret|api[_-]?key)\b\s*[=:]\s*['\"]?[^\s'\"]+",
    re.I,
)

_CHARS_PER_TOKEN = 2  # 中英文混合的保守估算


def mask_secrets(text: str) -> str:
    text = _SK_RE.sub("sk-****", text)
    text = _KV_RE.sub(r"\1****\2", text)
    return _PLAIN_KV_RE.sub(lambda m: f"{m.group(1)}=****", text)


def build_evidence(check: dict, samples: dict, settings) -> dict:
    """组装证据包。app_config 只挑非敏感字段，密钥从字段层面就不进入。"""
    evidence = {
        "check": check,
        "samples": {
            name: {"metrics": s.metrics, "evidence": list(s.evidence)}
            for name, s in samples.items()
        },
        "app_config": {
            "llm_base_url": settings.llm_base_url,
            "llm_model": settings.llm_model,
            "llm_timeout_s": settings.llm_timeout_s,
            "db_host": settings.db_host,
            "db_port": settings.db_port,
            "db_name": settings.db_name,
            "bank_api_urls": settings.bank_api_urls,
        },
    }
    # 兜底：序列化后整体脱敏再反序列化，防止 metrics/日志片段里带出密钥
    masked = mask_secrets(json.dumps(evidence, ensure_ascii=False))
    return json.loads(masked)


def estimate_tokens(evidence: dict) -> int:
    return len(json.dumps(evidence, ensure_ascii=False)) // _CHARS_PER_TOKEN


def truncate_evidence(evidence: dict, budget_tokens: int) -> dict:
    """超预算时按"最新错误优先"丢弃片段（evidence 列表新的在前，从尾部丢）。"""
    evidence = json.loads(json.dumps(evidence, ensure_ascii=False))  # 深拷贝
    truncated = False
    while estimate_tokens(evidence) > budget_tokens:
        longest_name, longest_len = None, 0
        for name, section in evidence.get("samples", {}).items():
            length = len(section.get("evidence") or [])
            if length > longest_len:
                longest_name, longest_len = name, length
        if longest_name is None:
            break  # 没有可丢的片段了
        evidence["samples"][longest_name]["evidence"].pop()  # 丢最旧的一条
        truncated = True
    evidence["truncated"] = truncated
    return evidence
```

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_evidence.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/diagnosis/__init__.py ops/src/diagnosis/evidence.py ops/tests/test_evidence.py
git commit -m "新增诊断证据包组装与脱敏截断"
```

---

### Task 10: LLM 客户端 + 提示词模板

**Files:**
- Create: `ops/src/diagnosis/llm.py`, `ops/src/diagnosis/prompts.py`, `ops/tests/test_llm_prompts.py`

**Interfaces:**
- Produces: `chat(settings, messages, transport=None) -> str`（返回 content 字符串；HTTP 非 200 抛 `httpx.HTTPStatusError`）；`SYSTEM_PROMPT`；`render_diagnosis_messages(check, evidence, runbook_body) -> list[dict]`。
- 约定：诊断输出要求 LLM 返回**严格 JSON**：`{"causes":[{"cause","confidence","basis"}],"suggestions":[{"step","detail"}]}`。

- [ ] **Step 1: 写失败测试** `ops/tests/test_llm_prompts.py`

```python
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from src.diagnosis.llm import chat
from src.diagnosis.prompts import SYSTEM_PROMPT, render_diagnosis_messages


def _llm_settings(settings):
    settings.llm_base_url = "http://gw:4000/v1"
    settings.llm_api_key = "sk-x"
    settings.llm_model = "deepseek"
    return settings


def test_chat_returns_content(settings):
    _llm_settings(settings)

    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "deepseek"
        assert body["messages"][0]["role"] == "system"
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"causes\":[]}"}}]})

    result = asyncio.run(
        chat(settings, [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
             transport=httpx.MockTransport(handler))
    )
    assert result == '{"causes":[]}'


def test_chat_raises_on_http_error(settings):
    _llm_settings(settings)

    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(chat(settings, [{"role": "user", "content": "u"}],
                         transport=httpx.MockTransport(handler)))


def test_render_messages_contract():
    check = {"id": "llm-latency", "title": "LLM 网关延迟", "level": "red", "message": "超时 45s"}
    evidence = {"check": check, "samples": {}, "app_config": {}}

    messages = render_diagnosis_messages(check, evidence, "网关超时手册正文")

    assert messages[0]["role"] == "system"
    assert "JSON" in messages[0]["content"]
    user = messages[1]["content"]
    assert "llm-latency" in user
    assert "超时 45s" in user
    assert "网关超时手册正文" in user


def test_render_messages_with_empty_runbook():
    check = {"id": "x", "title": "x", "level": "red", "message": "m"}
    messages = render_diagnosis_messages(check, {"samples": {}}, "")
    assert "（无匹配运维手册）" in messages[1]["content"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_llm_prompts.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`ops/src/diagnosis/llm.py`：

```python
from __future__ import annotations

import httpx


async def chat(settings, messages: list[dict], transport=None) -> str:
    """OpenAI 兼容网关单次 chat 调用，返回 content 字符串。"""
    headers = {}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"
    async with httpx.AsyncClient(
        timeout=settings.llm_timeout_s, transport=transport
    ) as client:
        resp = await client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            json={
                "model": settings.llm_model,
                "messages": messages,
                "temperature": 0.2,
            },
            headers=headers,
        )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
```

`ops/src/diagnosis/prompts.py`：

```python
from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "你是银行内网 Python 应用的运维诊断助手。值班人员不懂 Python，"
    "你的结论必须让非技术人员也能照着操作。\n"
    "基于给定的检查项、系统证据包和运维手册，输出**严格 JSON**（不要输出其他内容）：\n"
    '{"causes": [{"cause": "可能原因", "confidence": "高|中|低", "basis": "判断依据（引用证据）"}], '
    '"suggestions": [{"step": "第一步做什么", "detail": "具体操作，涉及文件给完整路径"}]}\n'
    "规则：原因按置信度从高到低排序；建议按操作顺序排列；"
    "只允许建议人工操作，你不执行任何动作；证据不足时在 basis 中明说。"
)

_TEMPLATE = """## 异常检查项
- ID：{check_id}
- 名称：{check_title}
- 级别：{check_level}
- 规则判定：{check_message}

## 运维手册
{runbook}

## 系统证据包（JSON）
{evidence_json}

请输出诊断结论 JSON。"""


def render_diagnosis_messages(check: dict, evidence: dict, runbook_body: str) -> list[dict]:
    user = _TEMPLATE.format(
        check_id=check.get("id", ""),
        check_title=check.get("title", ""),
        check_level=check.get("level", ""),
        check_message=check.get("message", ""),
        runbook=runbook_body or "（无匹配运维手册）",
        evidence_json=json.dumps(evidence, ensure_ascii=False, indent=2),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_llm_prompts.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/diagnosis/llm.py ops/src/diagnosis/prompts.py ops/tests/test_llm_prompts.py
git commit -m "新增 LLM 客户端与诊断提示词模板"
```

---

### Task 11: 诊断流水线

**Files:**
- Create: `ops/src/diagnosis/pipeline.py`, `ops/tests/test_diagnosis_pipeline.py`

**Interfaces:**
- Consumes: 前序全部模块。
- Produces: `Playbook`、`PLAYBOOKS`、`DEFAULT_PLAYBOOK`、`parse_conclusion(text)`、`run_diagnosis(...)`、`followup(...)`（签名见接口一览）。
- 返回结构约定：
  - 正常：`{"id", "check_id", "degraded": False, "conclusion": {"causes":[...], "suggestions":[...]}}`
  - 降级（LLM 失败）：`{"id", "check_id", "degraded": True, "rule_message": str, "runbook": str, "error": str}`

- [ ] **Step 1: 写失败测试** `ops/tests/test_diagnosis_pipeline.py`

```python
from __future__ import annotations

import asyncio
import json

import pytest

from src.collectors.base import Sample
from src.diagnosis.pipeline import (
    DEFAULT_PLAYBOOK,
    PLAYBOOKS,
    followup,
    parse_conclusion,
    run_diagnosis,
)
from src.storage import OpsDB


def _db(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    return db


def _collectors():
    async def fake(settings):
        return Sample("fake", True, metrics={"ok": 1})

    return {name: fake for name in
            ("process", "logs", "system", "database", "llm_gateway", "bank_api")}


async def _chat_ok(settings, messages):
    return json.dumps({
        "causes": [{"cause": "网关负载高", "confidence": "高", "basis": "延迟45s"}],
        "suggestions": [{"step": "联系网关管理员", "detail": "确认负载"}],
    }, ensure_ascii=False)


def test_parse_conclusion_tolerant():
    assert parse_conclusion('{"causes": [], "suggestions": []}') == {"causes": [], "suggestions": []}
    fenced = '前言```json\n{"causes": [{"cause": "x"}]}\n```后记'
    assert parse_conclusion(fenced)["causes"] == [{"cause": "x"}]
    assert parse_conclusion("不是JSON") == {"raw": "不是JSON"}


def test_playbooks_cover_builtin_rules():
    for check_id in ("process-alive", "health-timeout", "log-error-spike",
                     "disk-usage", "mysql-unreachable", "llm-latency", "bank-api"):
        assert check_id in PLAYBOOKS
    assert DEFAULT_PLAYBOOK.check_id == "*"


def test_run_diagnosis_success(settings):
    db = _db(settings)
    db.upsert_runbook("llm-timeout", "LLM 超时手册", "llm-timeout", "手册正文")

    result = asyncio.run(run_diagnosis(
        db, settings, "llm-latency", chat_fn=_chat_ok, collectors=_collectors(),
    ))

    assert result["degraded"] is False
    assert result["conclusion"]["causes"][0]["cause"] == "网关负载高"
    diag = db.get_diagnosis(result["id"])
    assert diag["playbook"] == "LLM 网关延迟诊断"
    transcript = json.loads(diag["transcript"])
    assert "手册正文" in transcript[1]["content"]   # runbook 已注入提示词


def test_run_diagnosis_degraded_when_llm_down(settings):
    db = _db(settings)
    db.upsert_runbook("llm-timeout", "LLM 超时手册", "llm-timeout", "手册正文")
    db.save_snapshot("red", json.dumps({
        "overall": "red",
        "checks": [{"id": "llm-latency", "title": "LLM 网关延迟",
                    "level": "red", "message": "LLM 网关响应严重超时（45s）"}],
        "samples": {},
    }))

    async def chat_down(settings, messages):
        raise ConnectionError("网关挂了")

    result = asyncio.run(run_diagnosis(
        db, settings, "llm-latency", chat_fn=chat_down, collectors=_collectors(),
    ))

    assert result["degraded"] is True
    assert result["rule_message"] == "LLM 网关响应严重超时（45s）"
    assert result["runbook"] == "手册正文"
    assert "网关挂了" in result["error"]


def test_followup_appends_and_returns(settings):
    db = _db(settings)
    first = asyncio.run(run_diagnosis(
        db, settings, "disk-usage", chat_fn=_chat_ok, collectors=_collectors(),
    ))

    async def chat_reply(settings, messages):
        assert messages[-1] == {"role": "user", "content": "怎么确认？"}
        return "看 disk_pct 指标"

    answer = asyncio.run(followup(db, settings, first["id"], "怎么确认？", chat_fn=chat_reply))
    assert answer["answer"] == "看 disk_pct 指标"

    transcript = json.loads(db.get_diagnosis(first["id"])["transcript"])
    assert transcript[-2:] == [
        {"role": "user", "content": "怎么确认？"},
        {"role": "assistant", "content": "看 disk_pct 指标"},
    ]

    with pytest.raises(KeyError):
        asyncio.run(followup(db, settings, 9999, "x", chat_fn=chat_reply))
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_diagnosis_pipeline.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现** `ops/src/diagnosis/pipeline.py`

```python
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from src.collectors import COLLECTORS
from src.collectors.base import run_collector
from src.diagnosis.evidence import build_evidence, truncate_evidence
from src.diagnosis.llm import chat
from src.diagnosis.prompts import render_diagnosis_messages


@dataclass
class Playbook:
    check_id: str
    title: str
    collectors: tuple
    runbook_category: str


PLAYBOOKS = {
    "process-alive": Playbook("process-alive", "进程宕机诊断", ("process", "logs"), "process-down"),
    "health-timeout": Playbook("health-timeout", "健康检查超时诊断", ("process", "logs", "system"), "health-slow"),
    "log-error-spike": Playbook("log-error-spike", "错误日志突增诊断", ("logs", "process", "llm_gateway", "bank_api", "database"), "error-spike"),
    "disk-usage": Playbook("disk-usage", "磁盘水位诊断", ("system",), "disk-full"),
    "mysql-unreachable": Playbook("mysql-unreachable", "数据库不可达诊断", ("database", "logs"), "mysql-unreachable"),
    "llm-latency": Playbook("llm-latency", "LLM 网关延迟诊断", ("llm_gateway", "logs"), "llm-timeout"),
    "bank-api": Playbook("bank-api", "银行接口异常诊断", ("bank_api", "logs"), "bank-api"),
}

DEFAULT_PLAYBOOK = Playbook(
    "*", "通用诊断",
    ("process", "logs", "system", "database", "llm_gateway", "bank_api"),
    "general",
)


def parse_conclusion(text: str) -> dict:
    """容错解析 LLM 输出：直接 JSON → ```json 代码块 → 原文兜底。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return {"raw": text}


def _find_check(db, check_id: str) -> dict:
    snapshot = db.latest_snapshot()
    if snapshot:
        for check in snapshot["payload"].get("checks", []):
            if check["id"] == check_id:
                return check
    return {"id": check_id, "title": check_id, "level": "gray", "message": "（无巡检快照）"}


async def run_diagnosis(db, settings, check_id, *, chat_fn=None, collectors=None) -> dict:
    """预编排诊断：剧本选采集器 → 证据包 → 单次 LLM 调用；LLM 失败则降级。"""
    chat_fn = chat_fn or chat
    collectors = collectors or COLLECTORS
    playbook = PLAYBOOKS.get(check_id, DEFAULT_PLAYBOOK)

    check = _find_check(db, check_id)
    samples_list = await asyncio.gather(*(
        run_collector(name, collectors[name], settings)
        for name in playbook.collectors
        if name in collectors
    ))
    samples = {s.collector: s for s in samples_list}
    evidence = truncate_evidence(
        build_evidence(check, samples, settings), settings.evidence_token_budget
    )
    runbook = db.get_runbook_by_category(playbook.runbook_category)
    runbook_body = runbook["body"] if runbook else ""
    messages = render_diagnosis_messages(check, evidence, runbook_body)

    degraded = False
    error = None
    reply = ""
    conclusion: dict = {}
    try:
        reply = await chat_fn(settings, messages)
        conclusion = parse_conclusion(reply)
    except Exception as exc:  # noqa: BLE001 - 降级是设计意图
        degraded = True
        error = f"{type(exc).__name__}: {exc}"

    transcript = list(messages)
    if reply:
        transcript.append({"role": "assistant", "content": reply})
    diagnosis_id = db.save_diagnosis(
        check_id, playbook.title,
        json.dumps(conclusion, ensure_ascii=False),
        json.dumps(transcript, ensure_ascii=False),
        degraded, error,
    )

    result = {"id": diagnosis_id, "check_id": check_id, "degraded": degraded}
    if degraded:
        result.update({
            "rule_message": check.get("message", ""),
            "runbook": runbook_body,
            "error": error,
        })
    else:
        result["conclusion"] = conclusion
    return result


async def followup(db, settings, diagnosis_id, question, *, chat_fn=None) -> dict:
    """追问：历史 transcript + 新问题 → 单次 LLM 调用，双方消息落库。"""
    chat_fn = chat_fn or chat
    diag = db.get_diagnosis(diagnosis_id)
    if diag is None:
        raise KeyError(f"诊断记录 {diagnosis_id} 不存在")
    transcript = json.loads(diag["transcript"])
    transcript.append({"role": "user", "content": question})
    answer = await chat_fn(settings, transcript)
    db.append_message(diagnosis_id, "user", question)
    db.append_message(diagnosis_id, "assistant", answer)
    return {"id": diagnosis_id, "answer": answer}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_diagnosis_pipeline.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/diagnosis/pipeline.py ops/tests/test_diagnosis_pipeline.py
git commit -m "新增预编排诊断流水线（含降级与追问）"
```

---

### Task 12: FastAPI 应用与路由

**Files:**
- Create: `ops/src/main.py`, `ops/tests/test_api.py`
- Create: `ops/web/static/.gitkeep`（占位，Task 13 填 index.html；StaticFiles 挂载需要目录存在）

**Interfaces:**
- Consumes: 前序全部模块。
- Produces: `create_app(settings=None, db=None) -> FastAPI`；模块级 `app = create_app()`。路由（除 `/api/health` 外均需令牌——仅当 `settings.ops_token` 非空时校验请求头 `X-Ops-Token`）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/health | ops 自身健康（免令牌） |
| GET | /api/inspections/latest | 最近快照；无快照返回 `{"overall":"gray","checks":[],"message":"尚未巡检"}` |
| GET | /api/inspections/history?limit=50 | 快照列表 |
| POST | /api/inspections/run | 立即巡检，返回 payload |
| POST | /api/diagnoses | body `{"check_id": str}`，返回诊断结果 |
| GET | /api/diagnoses/{id} | 诊断记录详情（含 conclusion/transcript 解析后内容） |
| POST | /api/diagnoses/{id}/followup | body `{"question": str}` |
| GET | /api/runbooks | runbook 列表 |
| GET | /api/runbooks/{slug} | runbook 详情 |
| POST | /api/runbooks | body `{"slug","title","category","body"}`（"存入知识库"用） |
| PUT | /api/runbooks/{slug} | 编辑 runbook |

- [ ] **Step 1: 写失败测试** `ops/tests/test_api.py`

```python
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import src.main as main_module
from src.main import create_app
from src.storage import OpsDB


@pytest.fixture
def client(settings, monkeypatch):
    settings.ops_token = "secret-token"
    db = OpsDB(settings.ops_db_path)
    db.init()

    async def fake_inspection(settings, db, rules, collectors=None):
        payload = {"created_at": "2026-08-06T00:00:00+00:00", "overall": "green",
                   "checks": [], "samples": {}}
        payload["id"] = db.save_snapshot("green", json.dumps(payload))
        return payload

    async def fake_diagnosis(db, settings, check_id, **kwargs):
        did = db.save_diagnosis(check_id, "测试剧本", '{"causes":[]}', "[]", False, None)
        return {"id": did, "check_id": check_id, "degraded": False,
                "conclusion": {"causes": []}}

    monkeypatch.setattr(main_module, "run_inspection", fake_inspection)
    monkeypatch.setattr(main_module, "run_diagnosis", fake_diagnosis)
    app = create_app(settings=settings, db=db)
    return TestClient(app)  # 不用 with 语法，避免触发 lifespan 定时循环


AUTH = {"X-Ops-Token": "secret-token"}


def test_health_is_open(client):
    assert client.get("/api/health").status_code == 200


def test_token_required(client):
    assert client.get("/api/inspections/latest").status_code == 401
    assert client.get("/api/inspections/latest", headers={"X-Ops-Token": "wrong"}).status_code == 401


def test_latest_snapshot_empty_then_present(client):
    resp = client.get("/api/inspections/latest", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["overall"] == "gray"

    run = client.post("/api/inspections/run", headers=AUTH)
    assert run.status_code == 200 and run.json()["overall"] == "green"

    latest = client.get("/api/inspections/latest", headers=AUTH).json()
    assert latest["overall"] == "green"
    history = client.get("/api/inspections/history", headers=AUTH).json()
    assert len(history) == 1


def test_diagnosis_create_and_get(client):
    resp = client.post("/api/diagnoses", json={"check_id": "llm-latency"}, headers=AUTH)
    assert resp.status_code == 200
    did = resp.json()["id"]

    detail = client.get(f"/api/diagnoses/{did}", headers=AUTH).json()
    assert detail["check_id"] == "llm-latency"
    assert detail["conclusion"] == {"causes": []}

    assert client.get("/api/diagnoses/9999", headers=AUTH).status_code == 404


def test_runbook_crud(client):
    resp = client.post("/api/runbooks", headers=AUTH, json={
        "slug": "disk-full", "title": "磁盘满", "category": "disk-full", "body": "清理日志",
    })
    assert resp.status_code == 200

    assert client.get("/api/runbooks", headers=AUTH).json()[0]["slug"] == "disk-full"

    resp = client.put("/api/runbooks/disk-full", headers=AUTH, json={
        "title": "磁盘满(更新)", "category": "disk-full", "body": "新正文",
    })
    assert resp.status_code == 200
    assert client.get("/api/runbooks/disk-full", headers=AUTH).json()["body"] == "新正文"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_api.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'src.main'`）

- [ ] **Step 3: 实现**

`ops/web/static/.gitkeep`：空文件。

`ops/src/main.py`：

```python
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import load_settings
from src.diagnosis.pipeline import followup, run_diagnosis
from src.inspection import run_inspection, scheduler_loop
from src.rules.engine import load_rules
from src.storage import OpsDB

logger = logging.getLogger("ops.main")

_OPS_DIR = Path(__file__).resolve().parents[1]
_RULES_PATH = Path(__file__).resolve().parent / "rules" / "rules.yaml"
_STATIC_DIR = _OPS_DIR / "web" / "static"


class DiagnoseRequest(BaseModel):
    check_id: str


class FollowupRequest(BaseModel):
    question: str


class RunbookRequest(BaseModel):
    slug: str
    title: str
    category: str
    body: str


class RunbookUpdateRequest(BaseModel):
    title: str
    category: str
    body: str


def create_app(settings=None, db=None) -> FastAPI:
    settings = settings or load_settings()
    if db is None:
        db = OpsDB(settings.ops_db_path)
        db.init()
    db.seed_runbooks(settings.seed_runbook_dir)
    rules = load_rules(_RULES_PATH)

    @asynccontextmanager
    async def lifespan(app):
        stop_event = asyncio.Event()
        task = asyncio.create_task(scheduler_loop(settings, db, rules, stop_event))
        yield
        stop_event.set()
        task.cancel()

    app = FastAPI(title="ops-assistant", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db

    def require_token(request: Request) -> None:
        if settings.ops_token and request.headers.get("X-Ops-Token") != settings.ops_token:
            raise HTTPException(status_code=401, detail="无效访问令牌")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/inspections/latest", dependencies=[Depends(require_token)])
    async def latest():
        snapshot = db.latest_snapshot()
        if snapshot is None:
            return {"overall": "gray", "checks": [], "message": "尚未巡检"}
        return snapshot

    @app.get("/api/inspections/history", dependencies=[Depends(require_token)])
    async def history(limit: int = 50):
        return db.list_snapshots(limit)

    @app.post("/api/inspections/run", dependencies=[Depends(require_token)])
    async def run_now():
        return await run_inspection(settings, db, rules)

    @app.post("/api/diagnoses", dependencies=[Depends(require_token)])
    async def diagnose(req: DiagnoseRequest):
        return await run_diagnosis(db, settings, req.check_id)

    @app.get("/api/diagnoses/{diagnosis_id}", dependencies=[Depends(require_token)])
    async def diagnosis_detail(diagnosis_id: int):
        diag = db.get_diagnosis(diagnosis_id)
        if diag is None:
            raise HTTPException(status_code=404, detail="诊断记录不存在")
        diag["conclusion"] = json.loads(diag["conclusion"])
        diag["transcript"] = json.loads(diag["transcript"])
        return diag

    @app.post("/api/diagnoses/{diagnosis_id}/followup", dependencies=[Depends(require_token)])
    async def diagnosis_followup(diagnosis_id: int, req: FollowupRequest):
        try:
            return await followup(db, settings, diagnosis_id, req.question)
        except KeyError:
            raise HTTPException(status_code=404, detail="诊断记录不存在") from None

    @app.get("/api/runbooks", dependencies=[Depends(require_token)])
    async def runbook_list():
        return db.list_runbooks()

    @app.get("/api/runbooks/{slug}", dependencies=[Depends(require_token)])
    async def runbook_detail(slug: str):
        runbook = db.get_runbook(slug)
        if runbook is None:
            raise HTTPException(status_code=404, detail="runbook 不存在")
        return runbook

    @app.post("/api/runbooks", dependencies=[Depends(require_token)])
    async def runbook_create(req: RunbookRequest):
        db.upsert_runbook(req.slug, req.title, req.category, req.body)
        return {"slug": req.slug}

    @app.put("/api/runbooks/{slug}", dependencies=[Depends(require_token)])
    async def runbook_update(slug: str, req: RunbookUpdateRequest):
        if db.get_runbook(slug) is None:
            raise HTTPException(status_code=404, detail="runbook 不存在")
        db.upsert_runbook(slug, req.title, req.category, req.body)
        return {"slug": slug}

    if _STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")

    return app


app = create_app()
```

注意：路由中对 `run_inspection` / `run_diagnosis` / `followup` 的调用保持模块级引用（`from src.inspection import run_inspection` 后在路由内直接调用），测试通过 `monkeypatch.setattr(src.main, "run_inspection", ...)` 替换——不要在路由内再 `import`。

- [ ] **Step 4: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_api.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ops/src/main.py ops/tests/test_api.py ops/web/static/.gitkeep
git commit -m "新增 ops-assistant FastAPI 应用与全部路由"
```

---

### Task 13: 前端单页仪表盘

**Files:**
- Create: `ops/web/static/index.html`（替换 .gitkeep 占位，可删除 .gitkeep）

**Interfaces:**
- Consumes: Task 12 的全部路由（fetch 时带 `X-Ops-Token` 头）。
- Produces: 无构建静态单页，三大区域：状态总览（红黄绿灰卡片）、巡检历史、诊断面板（结论渲染 + 追问 + 存入知识库 + runbook 编辑）。

- [ ] **Step 1: 实现** `ops/web/static/index.html`（无构建、无框架，完整实现如下）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ops-assistant 运维助手</title>
<style>
  :root { --green:#16a34a; --yellow:#d97706; --red:#dc2626; --gray:#9ca3af; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f3f4f6; color: #111827; }
  header { background: #1f2937; color: #fff; padding: 12px 20px;
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 18px; margin: 0; flex: 1; }
  header input { padding: 6px 8px; border-radius: 6px; border: none; width: 200px; }
  button { padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer;
           background: #2563eb; color: #fff; }
  button.ghost { background: #e5e7eb; color: #111827; }
  main { max-width: 1080px; margin: 20px auto; padding: 0 16px; }
  section { background: #fff; border-radius: 10px; padding: 16px 20px;
            margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  h2 { font-size: 16px; margin: 0 0 12px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
  .card { border-radius: 8px; padding: 12px; color: #fff; }
  .card.green { background: var(--green); } .card.yellow { background: var(--yellow); }
  .card.red { background: var(--red); } .card.gray { background: var(--gray); }
  .card .t { font-weight: 600; } .card .m { font-size: 13px; margin-top: 6px; opacity: .95; }
  .card button { margin-top: 8px; background: rgba(255,255,255,.25); }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  td, th { padding: 6px 8px; border-bottom: 1px solid #e5e7eb; text-align: left; }
  .badge { display: inline-block; padding: 1px 8px; border-radius: 10px; color: #fff; font-size: 12px; }
  pre { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px;
        padding: 10px; white-space: pre-wrap; word-break: break-all; font-size: 13px; }
  textarea { width: 100%; min-height: 120px; font-family: inherit; padding: 8px; }
  .row { display: flex; gap: 8px; margin-top: 8px; }
  .row input { flex: 1; padding: 8px; border: 1px solid #d1d5db; border-radius: 6px; }
  .cause { border-left: 3px solid var(--yellow); padding: 6px 10px; margin: 8px 0; background: #fffbeb; }
  .sugg { border-left: 3px solid var(--green); padding: 6px 10px; margin: 8px 0; background: #f0fdf4; }
  .muted { color: #6b7280; font-size: 13px; }
</style>
</head>
<body>
<header>
  <h1>ops-assistant 运维助手</h1>
  <input id="token" type="password" placeholder="访问令牌（如已配置）">
  <button class="ghost" onclick="saveToken()">保存令牌</button>
  <button onclick="runNow()">立即巡检</button>
</header>
<main>
  <section>
    <h2>状态总览 <span id="snapshot-time" class="muted"></span></h2>
    <div id="cards" class="cards"></div>
  </section>
  <section id="diag-panel" style="display:none">
    <h2>诊断结果</h2>
    <div id="diag-body"></div>
    <div class="row">
      <input id="followup-q" placeholder="追问，例如：我该怎么确认是网关负载问题？">
      <button onclick="askFollowup()">追问</button>
      <button class="ghost" onclick="saveAsRunbook()">存入知识库</button>
    </div>
    <div id="followup-log"></div>
  </section>
  <section>
    <h2>巡检历史</h2>
    <table><thead><tr><th>时间(UTC)</th><th>总体状态</th><th>摘要</th></tr></thead>
    <tbody id="history"></tbody></table>
  </section>
  <section>
    <h2>知识库（运维手册）</h2>
    <table><thead><tr><th>slug</th><th>标题</th><th>分类</th><th></th></tr></thead>
    <tbody id="runbooks"></tbody></table>
    <div id="rb-editor" style="display:none">
      <h2 id="rb-title"></h2>
      <textarea id="rb-body"></textarea>
      <div class="row"><button onclick="saveRunbook()">保存</button></div>
    </div>
  </section>
</main>
<script>
let currentDiagId = null;
let currentSlug = null;
const $ = id => document.getElementById(id);

function token() { return localStorage.getItem("ops_token") || ""; }
function saveToken() { localStorage.setItem("ops_token", $("token").value); refresh(); }
async function api(path, opts = {}) {
  opts.headers = Object.assign({"X-Ops-Token": token(), "Content-Type": "application/json"}, opts.headers || {});
  const resp = await fetch(path, opts);
  if (resp.status === 401) { alert("访问令牌无效，请在右上角输入"); throw new Error("401"); }
  if (!resp.ok) { alert("请求失败：" + resp.status); throw new Error(String(resp.status)); }
  return resp.json();
}
const LEVEL_LABEL = {green: "正常", yellow: "注意", red: "异常", gray: "未知"};

async function refresh() {
  const latest = await api("/api/inspections/latest");
  $("snapshot-time").textContent = latest.created_at ? "快照时间 " + latest.created_at : (latest.message || "");
  const cards = $("cards");
  cards.innerHTML = "";
  (latest.checks || []).forEach(c => {
    const div = document.createElement("div");
    div.className = "card " + c.level;
    div.innerHTML = `<div class="t">${c.title}</div><div class="m">${c.message}</div>`;
    if (c.level === "red" || c.level === "yellow") {
      const btn = document.createElement("button");
      btn.textContent = "诊断";
      btn.onclick = () => diagnose(c.id);
      div.appendChild(btn);
    }
    cards.appendChild(div);
  });
  const history = await api("/api/inspections/history?limit=20");
  $("history").innerHTML = history.map(s =>
    `<tr><td>${s.created_at}</td><td><span class="badge" style="background:var(--${s.overall})">${LEVEL_LABEL[s.overall] || s.overall}</span></td>` +
    `<td>${(s.payload.checks || []).filter(c => c.level !== "green").map(c => c.title).join("、") || "全部正常"}</td></tr>`
  ).join("");
  const rbs = await api("/api/runbooks");
  $("runbooks").innerHTML = rbs.map(r =>
    `<tr><td>${r.slug}</td><td>${r.title}</td><td>${r.category}</td>` +
    `<td><button class="ghost" onclick="editRunbook('${r.slug}')">编辑</button></td></tr>`
  ).join("");
}

async function runNow() { await api("/api/inspections/run", {method: "POST"}); await refresh(); }

async function diagnose(checkId) {
  $("diag-panel").style.display = "block";
  $("diag-body").innerHTML = "<p class='muted'>诊断中…</p>";
  $("followup-log").innerHTML = "";
  const result = await api("/api/diagnoses", {method: "POST", body: JSON.stringify({check_id: checkId})});
  currentDiagId = result.id;
  if (result.degraded) {
    $("diag-body").innerHTML =
      `<p><b>LLM 暂不可用</b>（${result.error}），以下为规则判定与运维手册：</p>` +
      `<pre>${result.rule_message}</pre><pre>${result.runbook || "（无匹配运维手册）"}</pre>`;
    return;
  }
  const c = result.conclusion;
  let html = "";
  (c.causes || []).forEach(x =>
    html += `<div class="cause"><b>[${x.confidence}]</b> ${x.cause}<br><span class="muted">依据：${x.basis}</span></div>`);
  (c.suggestions || []).forEach((x, i) =>
    html += `<div class="sugg"><b>建议 ${i + 1}：</b>${x.step}<br><span class="muted">${x.detail}</span></div>`);
  if (c.raw) html += `<pre>${c.raw}</pre>`;
  $("diag-body").innerHTML = html || "<p class='muted'>无结论</p>";
}

async function askFollowup() {
  const q = $("followup-q").value.trim();
  if (!q || !currentDiagId) return;
  const result = await api(`/api/diagnoses/${currentDiagId}/followup`, {method: "POST", body: JSON.stringify({question: q})});
  $("followup-log").innerHTML += `<p><b>问：</b>${q}</p><pre>${result.answer}</pre>`;
  $("followup-q").value = "";
}

async function saveAsRunbook() {
  const slug = prompt("runbook slug（英文短横线命名，如 llm-timeout）：");
  if (!slug) return;
  const title = prompt("标题：", slug) || slug;
  const body = $("diag-body").innerText;
  await api("/api/runbooks", {method: "POST",
    body: JSON.stringify({slug, title, category: slug, body: "# " + title + "\n\n" + body})});
  await refresh();
}

async function editRunbook(slug) {
  const rb = await api("/api/runbooks/" + slug);
  currentSlug = slug;
  $("rb-editor").style.display = "block";
  $("rb-title").textContent = "编辑：" + rb.title;
  $("rb-body").value = rb.body;
}

async function saveRunbook() {
  const rb = await api("/api/runbooks/" + currentSlug);
  await api("/api/runbooks/" + currentSlug, {method: "PUT", body: JSON.stringify({
    title: rb.title, category: rb.category, body: $("rb-body").value})});
  alert("已保存");
  await refresh();
}

$("token").value = token();
refresh();
</script>
</body>
</html>
```

- [ ] **Step 2: 人工验证**

Run: `cd ops && ../backend/venv/bin/python -m uvicorn src.main:app --port 9100`，浏览器打开 `http://127.0.0.1:9100/`，确认页面渲染、无快照时显示"尚未巡检"。Ctrl+C 停止。

- [ ] **Step 3: Commit**

```bash
git rm ops/web/static/.gitkeep 2>/dev/null; git add ops/web/static/index.html
git commit -m "新增运维助手前端单页仪表盘"
```

---

### Task 14: 出厂 runbook + 验收场景测试

**Files:**
- Create: `ops/runbooks/seed/process-down.md`, `ops/runbooks/seed/llm-timeout.md`, `ops/runbooks/seed/mysql-unreachable.md`, `ops/runbooks/seed/disk-full.md`, `ops/runbooks/seed/general.md`
- Create: `ops/tests/test_acceptance.py`

**Interfaces:**
- Consumes: 全部前序模块（验收测试走真实 `rules.yaml` + 真实规则引擎 + 真实流水线，仅替换采集器与 LLM）。
- Produces: 对应规格第 8 节验收标准 1、2 的自动化测试。

- [ ] **Step 1: 写出厂 runbook（内容即初始知识，从 DEPLOY 文档提炼）**

`ops/runbooks/seed/process-down.md`：

```markdown
# 主应用进程宕机

## 常见原因
- 进程崩溃（看日志末尾的 Traceback）
- 服务器重启后未启动服务
- 内存不足被系统 OOM Kill

## 处置步骤
1. 查看日志目录 `backend/data/logs/` 当天的 `app-*.log`，找最后的 ERROR/Traceback
2. 如是 OOM，联系系统管理员确认内存并考虑降低 LLM_MAX_TOKENS
3. 重启服务：`cd backend && bash scripts/server.sh start`
4. 重启后确认 `curl http://127.0.0.1:8000/health` 返回 ok
```

`ops/runbooks/seed/llm-timeout.md`：

```markdown
# LLM 网关超时 / 延迟过高

## 常见原因
- 网关侧负载高或模型服务重启中（探测能通但 chat 慢）
- LLM_API_KEY 失效（伴随 401/403 日志）
- 主应用 LLM_TIMEOUT_SECONDS 配置小于模型实际推理耗时

## 处置步骤
1. 看日志中是否有 401/403：有 → 联系网关管理员更新 key，改 `backend/.env` 的 LLM_API_KEY
2. 网关探测通但慢 → 联系网关管理员确认负载；临时可调大 `backend/.env` 的
   LLM_TIMEOUT_SECONDS（注意必须小于 nginx proxy_read_timeout）
3. 调整配置后重启主应用生效
```

`ops/runbooks/seed/mysql-unreachable.md`：

```markdown
# MySQL 不可达

## 常见原因
- MySQL 服务未启动或重启中
- 网络隔离/防火墙变更（生产 MySQL 在独立网段）
- 连接信息变更（host/port/密码轮换）

## 处置步骤
1. 联系 DBA 确认 MySQL 实例状态
2. 确认 `backend/.env` 的 DATABASE_HOST/PORT/USERNAME/PASSWORD 与 DBA 提供的一致
3. 若是密码轮换：更新 .env 后重启主应用
4. 数据库恢复前，主应用的会话历史与技能库功能不可用，但已生成报告不受影响
```

`ops/runbooks/seed/disk-full.md`：

```markdown
# 磁盘水位过高

## 常见原因
- 日志文件累积（默认保留 30 天）
- SQLite 数据库文件持续增长
- 历史部署 tar 包占用

## 处置步骤
1. 查看 `backend/data/logs/` 下最早日期的日志，归档或删除（需管理员确认）
2. 检查 `backend/data/*.db` 体积，checkpoints.db 过大可联系开发侧清理旧会话
3. 清理服务器上 `*.tar.gz` 历史部署包（保留最近 2 个）
4. 清理后在本页点"立即巡检"确认水位下降
```

`ops/runbooks/seed/general.md`：

```markdown
# 通用排查指引

1. 先看状态总览哪一项红/黄，从最严重的开始处理
2. 点"诊断"获取针对性分析；LLM 不可用时按页面展示的对应手册处理
3. 处置完成后点"立即巡检"验证恢复
4. 每次排障后点"存入知识库"沉淀经验，下次同类问题诊断会更准
```

- [ ] **Step 2: 写验收测试** `ops/tests/test_acceptance.py`

```python
"""验收场景（对应规格第 8 节）：

1. 主应用进程被杀 + 日志有报错 → 巡检出红，诊断给出可用结论
2. LLM 网关不可用 → 巡检照常出红黄绿，诊断降级展示规则判定 + runbook
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.collectors.base import Sample
from src.diagnosis.pipeline import run_diagnosis
from src.inspection import run_inspection
from src.rules.engine import load_rules
from src.storage import OpsDB

_RULES = load_rules(Path(__file__).resolve().parents[1] / "src" / "rules" / "rules.yaml")


def _db(settings):
    db = OpsDB(settings.ops_db_path)
    db.init()
    db.seed_runbooks(Path(__file__).resolve().parents[1] / "runbooks" / "seed")
    return db


def _down_collectors():
    """模拟主应用宕机：进程死、health 无响应、日志有报错、其余正常。"""
    async def process(s):
        return Sample("process", True, metrics={
            "pid": None, "alive": False,
            "health_ok": False, "health_status": None, "health_latency_ms": None,
        })

    async def logs(s):
        return Sample("logs", True, metrics={
            "error_count": 12, "warn_count": 0, "error_count_yesterday": 1,
            "clusters": {"memory": 12}, "files_scanned": 1,
        }, evidence=["ERROR MemoryError: unable to allocate"])

    def _ok(name, metrics):
        async def fn(s):
            return Sample(name, True, metrics=metrics)
        return fn

    return {
        "process": process,
        "logs": logs,
        "system": _ok("system", {"disk_pct": 40.0, "mem_pct": 95.0, "load1": 3.0}),
        "database": _ok("database", {"mode": "sqlite", "reachable": True, "files": []}),
        "llm_gateway": _ok("llm_gateway", {"configured": True, "reachable": True, "latency_s": 1.0, "error": None}),
        "bank_api": _ok("bank_api", {"endpoints": []}),
    }


def test_acceptance_main_app_down(settings):
    db = _db(settings)
    collectors = _down_collectors()

    payload = asyncio.run(run_inspection(settings, db, _RULES, collectors=collectors))
    assert payload["overall"] == "red"
    levels = {c["id"]: c["level"] for c in payload["checks"]}
    assert levels["process-alive"] == "red"
    assert levels["health-timeout"] == "red"
    assert levels["log-error-spike"] == "yellow"

    async def chat_ok(settings, messages):
        # 证据包必须包含进程状态与日志片段，供 LLM 定位
        assert '"alive": false' in messages[1]["content"]
        assert "MemoryError" in messages[1]["content"]
        return json.dumps({
            "causes": [{"cause": "内存不足被 OOM Kill", "confidence": "高",
                        "basis": "日志含 MemoryError 且内存 95%"}],
            "suggestions": [{"step": "重启主应用", "detail": "cd backend && bash scripts/server.sh start"}],
        }, ensure_ascii=False)

    result = asyncio.run(run_diagnosis(
        db, settings, "process-alive", chat_fn=chat_ok, collectors=collectors,
    ))
    assert result["degraded"] is False
    assert result["conclusion"]["causes"][0]["cause"] == "内存不足被 OOM Kill"


def test_acceptance_llm_down_degrades_to_runbook(settings):
    db = _db(settings)
    collectors = _down_collectors()

    async def chat_down(settings, messages):
        raise ConnectionError("网关不可达")

    result = asyncio.run(run_diagnosis(
        db, settings, "process-alive", chat_fn=chat_down, collectors=collectors,
    ))
    assert result["degraded"] is True
    assert result["rule_message"]                       # 规则判定原文
    assert "进程宕机" in result["runbook"]               # 出厂 process-down 手册全文
    assert "server.sh start" in result["runbook"]        # 手册里有可执行指引
```

- [ ] **Step 3: 运行确认通过**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/test_acceptance.py -v`
Expected: 2 passed

- [ ] **Step 4: Commit**

```bash
git add ops/runbooks/ ops/tests/test_acceptance.py
git commit -m "新增出厂 runbook 与验收场景测试"
```

---

### Task 15: 部署脚本、打包集成与最终验证

**Files:**
- Create: `ops/server.sh`, `ops/README.md`
- Modify: `scripts/build-offline-package.sh`（拷贝 ops 目录）
- Modify: `backend/scripts/start-offline.sh`（可选启动 ops-assistant）

**Interfaces:**
- Consumes: 全部前序模块。
- Produces: 生产可用的启动/打包链路。

- [ ] **Step 1: 实现** `ops/server.sh`

```bash
#!/usr/bin/env bash
#
# server.sh - ops-assistant 运维助手服务管理
# 用法: bash server.sh start|stop|restart|status|logs
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPS_DIR="$SCRIPT_DIR"
BACKEND_DIR="$(cd "$OPS_DIR/../backend" && pwd)"
PYTHON="$BACKEND_DIR/venv/bin/python"   # 复用主应用 venv，离线包已含全部依赖
RUN_DIR="$OPS_DIR/data/run"
LOG_DIR="$OPS_DIR/data/logs"
PID_FILE="$RUN_DIR/ops-assistant.pid"
RUNTIME_LOG="$LOG_DIR/ops.out.log"

ENV_FILE="$OPS_DIR/.env"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a
PORT="${OPS_PORT:-9100}"
HOST="${OPS_HOST:-0.0.0.0}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

is_running() { [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; }

case "${1:-help}" in
  start)
    if is_running; then log "已在运行 (pid $(cat "$PID_FILE"))"; exit 0; fi
    if [ ! -x "$PYTHON" ]; then log "错误：未找到主应用 venv（$PYTHON），请先完成主应用部署"; exit 1; fi
    cd "$OPS_DIR"
    nohup "$PYTHON" -m uvicorn src.main:app --host "$HOST" --port "$PORT" \
        >> "$RUNTIME_LOG" 2>&1 &
    echo $! > "$PID_FILE"
    log "ops-assistant 已启动 (pid $(cat "$PID_FILE"), 端口 $PORT)"
    ;;
  stop)
    if is_running; then kill "$(cat "$PID_FILE")" && log "已停止"; else log "未在运行"; fi
    rm -f "$PID_FILE"
    ;;
  restart)
    "$0" stop || true
    "$0" start
    ;;
  status)
    if is_running; then log "运行中 (pid $(cat "$PID_FILE"), 端口 $PORT)"; else log "未运行"; exit 1; fi
    ;;
  logs)
    tail -n "${2:-200}" -f "$RUNTIME_LOG"
    ;;
  *)
    echo "用法: bash server.sh start|stop|restart|status|logs"
    ;;
esac
```

- [ ] **Step 2: 集成打包脚本** `scripts/build-offline-package.sh`

在 `cp -a "$ROOT_DIR/backend" "$STAGE_DIR/backend"`（约第 51 行）之后插入：

```bash
cp -a "$ROOT_DIR/ops" "$STAGE_DIR/ops"
rm -rf "$STAGE_DIR/ops/data" "$STAGE_DIR/ops/__pycache__" \
    "$STAGE_DIR/ops/src/__pycache__" "$STAGE_DIR/ops/tests/__pycache__"
```

- [ ] **Step 3: 集成启动脚本** `backend/scripts/start-offline.sh`

该脚本第 22 行已定义 `ROOT_DIR`（部署包根目录，`backend/` 与 `ops/` 的父目录）。在文件末尾主应用前台启动 uvicorn 的 `cd "$BACKEND_DIR"` 一行**之前**插入：

```bash
# 可选启动运维助手 ops-assistant（失败不影响主应用）
if [ -f "$ROOT_DIR/ops/server.sh" ]; then
    read -r -p "是否启动运维助手 ops-assistant? [Y/n]: " INPUT_START_OPS
    if [[ ! "${INPUT_START_OPS:-Y}" =~ ^[Nn]$ ]]; then
        bash "$ROOT_DIR/ops/server.sh" start || echo "ops-assistant 启动失败，不影响主应用"
    fi
fi
```

- [ ] **Step 4: 写** `ops/README.md`

```markdown
# ops-assistant 运维助手

独立的只读运维工具：定时巡检（红黄绿）+ 大模型辅助诊断 + 可编辑运维手册。

## 值班人员使用

1. 浏览器打开 `http://<服务器IP>:9100/`（如配置了访问令牌，先填入右上角）
2. 状态总览红/黄卡片 → 点"诊断" → 按结论中的"建议操作"人工执行
3. LLM 不可用时，页面自动降级展示规则判定和对应运维手册
4. 排障完成后点"存入知识库"，沉淀经验

## 管理命令

```bash
bash ops/server.sh start|stop|restart|status|logs
```

建议由系统管理员为 ops-assistant 配置 systemd 或 crontab 保活（与主应用相同手段），
避免运维工具自身意外退出后无人察觉。

## 配置

全部配置见 `ops/.env.example`，均可选；未配置时自动从主应用 `backend/.env` 推断
（LLM 网关、数据库、银行接口地址等）。`OPS_TOKEN` 设置后页面需带令牌访问。

## 安全约束

- 只读：不修改主应用任何文件/数据，所有处置动作由人执行
- 密钥（LLM key / 数据库口令 / 银行 token）不会出现在页面与诊断内容中
```

- [ ] **Step 5: 全量测试 + 语法检查**

Run: `cd ops && ../backend/venv/bin/python -m pytest tests/ -v`
Expected: 全部通过（约 40 例）

Run: `bash -n ops/server.sh && bash -n scripts/build-offline-package.sh && bash -n backend/scripts/start-offline.sh`
Expected: 无输出（语法正确）

- [ ] **Step 6: 冒烟验证**

```bash
cd ops && ../backend/venv/bin/python -m uvicorn src.main:app --port 9100 &
sleep 3
curl -s http://127.0.0.1:9100/api/health        # {"status":"ok"}
curl -s http://127.0.0.1:9100/ | head -5        # 返回 index.html
kill %1
```

- [ ] **Step 7: Commit**

```bash
git add ops/server.sh ops/README.md scripts/build-offline-package.sh backend/scripts/start-offline.sh
git commit -m "新增 ops-assistant 部署脚本与离线包集成"
```

---

## 完成判定

- [ ] `cd ops && ../backend/venv/bin/python -m pytest tests/ -v` 全绿
- [ ] 规格第 8 节三条验收标准均有对应测试或人工验证记录
- [ ] `git log` 中每个 Task 一个独立提交
