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
    FORCE=false
    [ "${2:-}" = "--force" ] && FORCE=true
    if is_running; then
      PID="$(cat "$PID_FILE")"
      kill "$PID" 2>/dev/null || true
      for _ in $(seq 1 10); do
        kill -0 "$PID" 2>/dev/null || break
        sleep 1
      done
      if kill -0 "$PID" 2>/dev/null; then
        if [ "$FORCE" = true ]; then
          kill -9 "$PID" 2>/dev/null || true
          log "已强制停止 (SIGKILL, pid $PID)"
        else
          log "停止超时，进程仍在运行 (pid $PID)，可执行: bash server.sh stop --force"
          exit 1
        fi
      else
        log "已停止"
      fi
    else
      log "未在运行"
    fi
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
