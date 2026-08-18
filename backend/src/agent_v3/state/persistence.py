"""agent_v3 持久化 checkpointer 接线（P2）。

框架自带 PersistenceCheckpointer（openjiuwen core.session.checkpointer.persistence），
SQLite 走 SQLAlchemy sqlite+aiosqlite + WAL + DbBasedKVStore（kv_store 表，
首次读写自动建表）。这里负责：

- init_v3_checkpointer：按 conf 创建并设为全局默认（lifespan startup，Runner.start 之前）；
- close_v3_checkpointer：lifespan shutdown 释放（dispose engine + 置空默认）；
- delete_v3_thread_checkpoint：删除会话时按键前缀清理该 thread 的 checkpoint。

checkpoint blob 只有框架自己读写（续聊状态）；应用层重载只读业务表，
不在这里提供任何"读 checkpoint"的接口。

conf 预留 MySQL 通道（db_client 传预构 AsyncEngine），本阶段只验证 SQLite。
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3

import aiosqlite
from openjiuwen.core.session.checkpointer import CheckpointerFactory
from openjiuwen.core.session.checkpointer.checkpointer import CheckpointerConfig

from src.config import get_settings, resolve_path

logger = logging.getLogger("njbank.agent")

_SQLITE_LOCK_TIMEOUT_S = 5

_checkpointer = None
_lock = asyncio.Lock()


async def init_v3_checkpointer() -> None:
    """创建 persistence checkpointer 并设为框架全局默认（幂等）。"""
    global _checkpointer
    if _checkpointer is not None:
        return
    async with _lock:
        if _checkpointer is not None:
            return
        settings = get_settings()
        db_path = resolve_path(settings.agent_v3_checkpointer_db_path)
        checkpointer = await CheckpointerFactory.create(
            CheckpointerConfig(
                type="persistence",
                conf={
                    "db_type": "sqlite",
                    "db_path": str(db_path),
                    "db_timeout": _SQLITE_LOCK_TIMEOUT_S,
                    "db_enable_wal": True,
                },
            )
        )
        CheckpointerFactory.set_default_checkpointer(checkpointer)
        _checkpointer = checkpointer
        logger.info("agent_v3 checkpointer initialized: %s", db_path)


async def close_v3_checkpointer() -> None:
    """释放 checkpointer（dispose engine）并恢复框架默认（in_memory）。"""
    global _checkpointer
    checkpointer, _checkpointer = _checkpointer, None
    if checkpointer is None:
        return
    kv_store = getattr(checkpointer, "_kv_store", None)
    engine = getattr(kv_store, "engine", None)
    if engine is not None:
        try:
            await engine.dispose()
        except Exception:
            logger.exception("agent_v3 checkpointer engine dispose failed")
    CheckpointerFactory.set_default_checkpointer(None)
    logger.info("agent_v3 checkpointer closed")


async def delete_v3_thread_checkpoint(thread_id: str) -> None:
    """删除某 thread 的 v3 checkpoint：kv_store 表按键前缀 `{thread_id}:` 删除。

    键结构（框架 build_key_with_namespace）：
    `{session_id}:agent:{agent_id}:agent_state_blobs` 与 `…_dump_type`。
    文件不存在或表不存在（从未写入）时静默跳过。
    """
    thread_id = str(thread_id or "").strip()
    if not thread_id:
        return
    db_path = resolve_path(get_settings().agent_v3_checkpointer_db_path)
    if not db_path.exists():
        return
    connection = await aiosqlite.connect(str(db_path))
    try:
        await connection.execute(
            "DELETE FROM kv_store WHERE key LIKE ? ESCAPE '\\'",
            (f"{thread_id}:%",),
        )
        await connection.commit()
        logger.info("agent_v3 checkpoint cleared: thread_id=%s", thread_id)
    except sqlite3.OperationalError:
        # kv_store 表不存在（该库从未写入 checkpoint），无需清理
        pass
    except Exception:
        logger.exception("agent_v3 checkpoint clear failed: thread_id=%s", thread_id)
    finally:
        await connection.close()
