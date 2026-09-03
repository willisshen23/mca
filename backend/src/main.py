from __future__ import annotations

import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from fastapi import Request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.routes import router
from src.config import get_settings

settings = get_settings()

# 后台任务强引用（防 GC 提前回收），目前用于 lifespan 预热任务。
_background_tasks: set[asyncio.Task] = set()


class SpaStaticFiles(StaticFiles):
    """Serve index.html for Vue history-mode routes such as /chat-ui."""

    @staticmethod
    def _is_frontend_route(path: str) -> bool:
        normalized = path.strip("/")
        if not normalized:
            return False
        if normalized == "api" or normalized.startswith(("api/", "assets/")):
            return False
        # Missing files keep their real 404 response; extensionless paths are
        # treated as Vue Router history-mode routes.
        return not Path(normalized).suffix

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._is_frontend_route(path):
                raise
        else:
            if response.status_code != 404 or not self._is_frontend_route(path):
                return response
        return await super().get_response("index.html", scope)


def _resolve_log_level(level_name: str) -> int:
    level = getattr(logging, str(level_name or "INFO").upper(), None)
    return level if isinstance(level, int) else logging.INFO


log_level = _resolve_log_level(settings.log_level)
_log_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class DatedTimedRotatingFileHandler(TimedRotatingFileHandler):
    """按天切分日志，文件名内含日期stem>-YYYY-MM-DD<ext>（如 app-2026-06-25.log）"

    这样可以直接从文件名看出该日志属于哪一天；午夜自动切换到新的带日期文件"
    并按 backup_count 保留最近若干天的日志"
    """

    def __init__(self, log_dir: Path, base_name: str, backup_count: int):
        self._log_dir = log_dir
        base = Path(base_name)
        self._stem = base.stem or "app"
        self._ext = base.suffix or ".log"
        super().__init__(
            self._dated_path(),
            when="midnight",
            backupCount=backup_count,
            encoding="utf-8",
        )

    def _dated_path(self) -> str:
        return str(self._log_dir / f"{self._stem}-{datetime.now():%Y-%m-%d}{self._ext}")

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None
        # 切换到新一天的带日期文件，而不是给旧文件追加后缀"
        self.baseFilename = self._dated_path()
        if not self.delay:
            self.stream = self._open()
        current_time = int(time.time())
        new_rollover_at = self.computeRollover(current_time)
        while new_rollover_at <= current_time:
            new_rollover_at += self.interval
        self.rolloverAt = new_rollover_at
        self._purge_old_logs()

    def _purge_old_logs(self) -> None:
        if self.backupCount <= 0:
            return
        # 文件名中的日期为 YYYY-MM-DD，按字典序排序即按时间排序，删除最旧的"
        files = sorted(self._log_dir.glob(f"{self._stem}-*{self._ext}"))
        for stale in files[: max(0, len(files) - self.backupCount)]:
            try:
                stale.unlink()
            except OSError:
                pass


def _build_file_handler() -> TimedRotatingFileHandler | None:
    """Create a dated, daily-rotating file handler so logs are persisted across restarts."""
    if not settings.log_to_file:
        return None
    log_dir = Path(settings.log_dir)
    if not log_dir.is_absolute():
        log_dir = Path(__file__).resolve().parent.parent / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = DatedTimedRotatingFileHandler(
        log_dir=log_dir,
        base_name=settings.log_file,
        backup_count=settings.log_file_backup_count,
    )
    handler.setFormatter(_log_formatter)
    handler.setLevel(log_level)
    return handler


_file_handler = _build_file_handler()

_log = logging.getLogger("activity-analysis.agent")
_log.setLevel(log_level)
if not _log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(_log_formatter)
    _log.addHandler(_handler)
    if _file_handler is not None:
        _log.addHandler(_file_handler)
_log.propagate = False

# Persist uvicorn server/access logs to the same dated log file.
if _file_handler is not None:
    for _uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        _uvicorn_logger = logging.getLogger(_uvicorn_logger_name)
        if _file_handler not in _uvicorn_logger.handlers:
            _uvicorn_logger.addHandler(_file_handler)
        # Avoid double writes: each logger carries the handler itself, so
        # propagating to a parent that shares the same handler would duplicate.
        _uvicorn_logger.propagate = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: 确保数据库表已创"
    from src.infrastructure.db.models import Base
    from src.infrastructure.db.session import engine
    from sqlalchemy import inspect
    inspector = inspect(engine)
    # Align legacy agent_run_history.request_id (length/charset/collation)
    # before creating report_versions, whose FK references it; otherwise
    # MySQL aborts table creation with error 3780 on older deployments.
    from src.infrastructure.db.migrations import ensure_request_id_fk_compatible

    ensure_request_id_fk_compatible(engine)
    # MySQL may return reflected table names in lowercase when
    # lower_case_table_names=1, while SQLite preserves the model's original
    # spelling (for example SYSTEM_PROMPT). Compare normalized names so an
    # existing MySQL table is not mistaken for a missing table.
    existing = {name.casefold() for name in inspector.get_table_names()}
    for table in Base.metadata.sorted_tables:
        normalized_name = table.name.casefold()
        if normalized_name not in existing:
            table.create(bind=engine, checkfirst=True)
            existing.add(normalized_name)
            _log.info("Created table: %s", table.name)
    from src.infrastructure.db.migrations import (
        cleanup_v1_data,
        ensure_agent_version_column,
        ensure_conversation_turn_schema,
        ensure_usage_event_schema,
    )
    ensure_agent_version_column(engine)
    ensure_conversation_turn_schema(engine)
    ensure_usage_event_schema(engine)
    # Add missing agent_run_history columns BEFORE cleanup_v1_data: the
    # cleanup queries AgentRunHistory via the ORM, which SELECTs every mapped
    # column, so it crashes on legacy databases missing newer columns.
    from src.services.agent_run_history_service import ensure_agent_run_history_schema

    ensure_agent_run_history_schema()
    await cleanup_v1_data(engine)

    from src.services.agent_run_history_service import (
        ensure_report_versions_schema,
    )
    ensure_report_versions_schema()
    from src.services.skill_service import ensure_skill_usage_schema
    ensure_skill_usage_schema()

    # startup: agent_v3（openjiuwen）无条件初始化
    from openjiuwen.core.runner import Runner

    from src.agent_v3.state.persistence import init_v3_checkpointer

    # checkpointer 须在 Runner.start 之前设为全局默认，
    # 保证首轮 pre_run 的 recover 就走持久化
    await init_v3_checkpointer()
    await Runner.start()
    _log.info("agent_v3: openjiuwen Runner started")

    # 后台预热（不阻塞启动，失败不影响服务，运行期各自有兜底）：
    # 1) tiktoken 词表首次加载需联网，离线环境会同步阻塞到 TCP 超时（约 1 分钟），
    #    放工作线程提前触发，避免首个用户任务冻结事件循环；
    # 2) ReActAgent 首次组装有一次性成本，提前完成（内部有锁，与首个请求并发安全）。
    async def _warm_runtime() -> None:
        from src.utils.token_budget import warm_token_estimator

        try:
            await asyncio.to_thread(warm_token_estimator)
        except Exception:
            _log.exception("tiktoken 词表预热失败（运行期退化为字符估算）")
        try:
            from src.agent_v3.agent_factory import get_v3_agent

            await get_v3_agent()
            _log.info("agent_v3: 智能体预热完成")
        except Exception:
            _log.exception("agent_v3: 智能体预热失败（首个任务将按需重建）")

    warmup_task = asyncio.create_task(_warm_runtime())
    _background_tasks.add(warmup_task)
    warmup_task.add_done_callback(_background_tasks.discard)

    yield

    # shutdown: 释放 agent_v3 资源
    from src.agent_v3.agent_factory import close_v3_agent
    from src.agent_v3.state.persistence import close_v3_checkpointer

    await close_v3_agent()
    await Runner.stop()
    await close_v3_checkpointer()
    _log.info("agent_v3: openjiuwen Runner stopped")


app = FastAPI(title="活动分析助手", lifespan=lifespan)

origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.middleware("http")
async def log_api_request(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        _log.info(
            "api_request method=%s path=%s status=%s cost_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


static_dir = Path(__file__).parent / "infrastructure" / "static"
if static_dir.exists() and list(static_dir.iterdir()):
    app.mount("/", SpaStaticFiles(directory=str(static_dir), html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        log_level=log_level,
        reload=True,
    )
