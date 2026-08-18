from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess
import threading
import time

from fastapi import APIRouter, HTTPException

from src.api.schemas import EnvConfigUpdate
from src.services.env_config_service import _read_env_values, get_env_config, update_env_config, update_env_config_content

logger = logging.getLogger("njbank.agent")

router = APIRouter(prefix="/env-config")
_restart_lock = threading.Lock()
_restart_scheduled = False


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def _restart_command() -> tuple[str | list[str], bool, Path]:
    backend_dir = _backend_dir()
    script_path = backend_dir / "scripts" / "server.sh"
    configured_command = os.getenv("BACKEND_RESTART_COMMAND", "").strip()
    if not configured_command:
        configured_command = _read_env_values().get("BACKEND_RESTART_COMMAND", "").strip()

    if configured_command:
        return (
            configured_command.format(backend_dir=backend_dir, script=script_path),
            True,
            backend_dir,
        )

    if not script_path.exists():
        raise RuntimeError("未配置 BACKEND_RESTART_COMMAND，且未找到 backend/scripts/server.sh")

    return ["bash", str(script_path), "restart"], False, backend_dir


def _subprocess_options(cwd: Path) -> dict:
    options: dict = {
        "cwd": str(cwd),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        options["start_new_session"] = True
    return options


def _restart_process_later(command: str | list[str], shell: bool, cwd: Path, delay_seconds: float = 0.8) -> None:
    def runner() -> None:
        global _restart_scheduled
        time.sleep(delay_seconds)
        logger.warning("backend_restart executing command=%s", command)
        try:
            subprocess.Popen(command, shell=shell, **_subprocess_options(cwd))
        except Exception as exc:
            _restart_scheduled = False
            logger.exception("backend_restart failed: %s", exc)

    thread = threading.Thread(target=runner, name="backend-restart", daemon=True)
    thread.start()


@router.get("")
async def api_get_env_config():
    started = time.perf_counter()
    payload = get_env_config()
    logger.info(
        "env_config_api get groups=%d cost_ms=%.2f",
        len(payload.get("groups") or []),
        (time.perf_counter() - started) * 1000,
    )
    return payload


@router.patch("")
async def api_update_env_config(body: EnvConfigUpdate):
    started = time.perf_counter()
    try:
        payload = update_env_config_content(body.content) if body.content is not None else update_env_config(body.values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "env_config_api update mode=%s keys=%d content_chars=%d restart_required=%s cost_ms=%.2f",
        "content" if body.content is not None else "values",
        len(body.values),
        len(body.content or ""),
        payload.get("restart_required"),
        (time.perf_counter() - started) * 1000,
    )
    return payload


@router.post("/restart")
async def api_restart_backend():
    global _restart_scheduled
    with _restart_lock:
        if _restart_scheduled:
            return {
                "restart_scheduled": True,
                "message": "后端重启已在执行中，请稍候。",
            }
        try:
            command, shell, cwd = _restart_command()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        _restart_scheduled = True
    logger.warning("backend_restart scheduled command=%s", command)
    _restart_process_later(command, shell, cwd)
    return {
        "restart_scheduled": True,
        "message": "后端重启脚本已触发，服务将在数秒后恢复。",
    }
