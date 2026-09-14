#!/usr/bin/env bash
#
# server.sh - production helper for activity analysis assistant backend service.
# It manages the FastAPI process with a pid file and runtime log file.
#
# Usage:
#   bash scripts/server.sh start
#   bash scripts/server.sh stop
#   bash scripts/server.sh restart
#   bash scripts/server.sh status
#   bash scripts/server.sh logs
#   bash scripts/server.sh help
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$BACKEND_DIR/venv"
ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"
RUN_DIR="$BACKEND_DIR/data/run"
LOG_DIR="$BACKEND_DIR/data/logs"
PID_FILE="$RUN_DIR/activity-analysis-assistant.pid"
RUNTIME_LOG="$LOG_DIR/uvicorn.out.log"
APP_MODULE="src.main:app"

DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8000"
DEFAULT_LOG_LEVEL="info"

usage() {
    cat <<'EOF'
活动分析助手 service helper

Commands:
  start       Start service in background
  stop        Stop service by pid file
  restart     Stop and start service
  status      Show service status
  logs        Follow runtime log
  help        Show this help

Options:
  logs -n 200          Show last 200 lines, then follow
  logs --no-follow     Print log and exit
  start --reinstall    Reinstall Python dependencies before start
  stop --force         Send SIGKILL if graceful stop fails

Environment:
  HOST                 Bind host, default reads .env or 0.0.0.0
  PORT                 Bind port, default reads .env or 8000
  LOG_LEVEL            Uvicorn log level, default reads .env or info
  PYTHON_BIN           Python executable used to create venv
EOF
}

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
    log "ERROR: $*"
    exit 1
}

read_env_value() {
    local key="$1"
    local default_value="$2"
    local value=""

    if [ -f "$ENV_FILE" ]; then
        value="$(
            grep -E "^${key}=" "$ENV_FILE" 2>/dev/null \
                | tail -n 1 \
                | cut -d'=' -f2- \
                | sed -E 's/[[:space:]]*#.*$//' \
                | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' \
                | sed -E 's/^"//; s/"$//; s/^'\''//; s/'\''$//'
        )"
    fi

    if [ -n "$value" ]; then
        printf '%s' "$value"
    else
        printf '%s' "$default_value"
    fi
}

load_env() {
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_EXAMPLE" ]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            log "Created .env from .env.example. Please verify production values."
        else
            die "Missing .env and .env.example in $BACKEND_DIR"
        fi
    fi

    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a

    HOST="${HOST:-$(read_env_value HOST "$DEFAULT_HOST")}"
    PORT="${PORT:-$(read_env_value PORT "$DEFAULT_PORT")}"
    LOG_LEVEL="${LOG_LEVEL:-$(read_env_value LOG_LEVEL "$DEFAULT_LOG_LEVEL")}"
    # uvicorn --log-level 只接受小写（critical/error/warning/info/debug/trace），
    # 而 .env 里 LOG_LEVEL 按 Python logging 惯例写成大写 INFO
    LOG_LEVEL="$(printf '%s' "$LOG_LEVEL" | tr '[:upper:]' '[:lower:]')"
}

find_python() {
    if [ -n "${PYTHON_BIN:-}" ]; then
        command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "PYTHON_BIN not found: $PYTHON_BIN"
        printf '%s' "$PYTHON_BIN"
        return
    fi

    local cmd
    for cmd in python3.12 python3.11 python3.10 python3; do
        if command -v "$cmd" >/dev/null 2>&1; then
            printf '%s' "$cmd"
            return
        fi
    done

    die "Python 3.10+ was not found"
}

ensure_dirs() {
    mkdir -p "$RUN_DIR" "$LOG_DIR" "$BACKEND_DIR/data/uploads" "$BACKEND_DIR/data/outputs"
}

ensure_venv() {
    local python_bin="$1"

    if [ ! -x "$VENV_DIR/bin/python" ]; then
        log "Creating venv: $VENV_DIR"
        "$python_bin" -m venv "$VENV_DIR"
    fi
}

install_deps_if_needed() {
    local reinstall="${1:-false}"
    local marker="$VENV_DIR/.deps-installed"

    if [ "$reinstall" != "true" ] && [ -f "$marker" ]; then
        return
    fi

    log "Installing Python dependencies"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

    # wheels/ 离线包目录按目标平台构建（如 Linux aarch64 靶机）；平台不匹配时
    # --no-index 会报 "No matching distribution"，回落在线安装
    local use_offline=false
    if [ -d "$BACKEND_DIR/wheels" ] && ls "$BACKEND_DIR/wheels"/*.whl >/dev/null 2>&1; then
        local os_tag=""
        case "$(uname -s)" in
            Linux)  os_tag="manylinux" ;;
            Darwin) os_tag="macosx" ;;
        esac
        if [ -n "$os_tag" ] && ls "$BACKEND_DIR/wheels"/*"$os_tag"*.whl >/dev/null 2>&1; then
            use_offline=true
        fi
    fi

    if [ "$use_offline" = "true" ]; then
        pip install --no-index --find-links="$BACKEND_DIR/wheels" -r "$BACKEND_DIR/requirements.txt"
    else
        pip install -r "$BACKEND_DIR/requirements.txt"
    fi

    date '+%Y-%m-%d %H:%M:%S' > "$marker"
}

pid_from_file() {
    if [ -f "$PID_FILE" ]; then
        tr -dc '0-9' < "$PID_FILE"
    fi
}

is_running() {
    local pid="${1:-}"
    [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1
}

cleanup_stale_pid() {
    local pid
    pid="$(pid_from_file)"
    if [ -n "$pid" ] && ! is_running "$pid"; then
        log "Removing stale pid file: $PID_FILE"
        rm -f "$PID_FILE"
    fi
}

start_service() {
    local reinstall="false"
    if [ "${1:-}" = "--reinstall" ]; then
        reinstall="true"
    fi

    ensure_dirs
    cleanup_stale_pid

    local current_pid
    current_pid="$(pid_from_file)"
    if is_running "$current_pid"; then
        log "Service is already running, pid=$current_pid"
        return
    fi

    load_env
    local python_bin
    python_bin="$(find_python)"
    ensure_venv "$python_bin"
    install_deps_if_needed "$reinstall"

    log "Applying database SQL"
    bash "$SCRIPT_DIR/migrate-db.sh" auto

    log "Starting service on ${HOST}:${PORT}"
    cd "$BACKEND_DIR"
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

    nohup python -m uvicorn "$APP_MODULE" \
        --host "$HOST" \
        --port "$PORT" \
        --log-level "$LOG_LEVEL" \
        </dev/null >> "$RUNTIME_LOG" 2>&1 &

    local pid="$!"
    printf '%s' "$pid" > "$PID_FILE"
    sleep 1

    if is_running "$pid"; then
        log "Service started, pid=$pid"
        log "Runtime log: $RUNTIME_LOG"
        log "Health check: http://127.0.0.1:${PORT}/activity/health"
    else
        rm -f "$PID_FILE"
        die "Service failed to start. Check $RUNTIME_LOG"
    fi
}

stop_service() {
    local force="false"
    if [ "${1:-}" = "--force" ]; then
        force="true"
    fi

    local pid
    pid="$(pid_from_file)"
    if [ -z "$pid" ]; then
        log "Service is not running: no pid file"
        return
    fi

    if ! is_running "$pid"; then
        log "Service is not running, removing stale pid file"
        rm -f "$PID_FILE"
        return
    fi

    log "Stopping service, pid=$pid"
    kill "$pid" >/dev/null 2>&1 || true

    local i
    for i in $(seq 1 20); do
        if ! is_running "$pid"; then
            rm -f "$PID_FILE"
            log "Service stopped"
            return
        fi
        sleep 1
    done

    if [ "$force" = "true" ]; then
        log "Graceful stop timed out, killing pid=$pid"
        kill -9 "$pid" >/dev/null 2>&1 || true
        rm -f "$PID_FILE"
        log "Service killed"
        return
    fi

    die "Graceful stop timed out. Run: bash scripts/server.sh stop --force"
}

status_service() {
    cleanup_stale_pid
    load_env

    local pid
    pid="$(pid_from_file)"
    if is_running "$pid"; then
        log "Service is running"
        printf 'PID: %s\n' "$pid"
        printf 'URL: http://127.0.0.1:%s\n' "$PORT"
        printf 'Health: http://127.0.0.1:%s/activity/health\n' "$PORT"
        printf 'Runtime log: %s\n' "$RUNTIME_LOG"
    else
        log "Service is stopped"
    fi
}

show_logs() {
    local lines="100"
    local follow="true"

    while [ $# -gt 0 ]; do
        case "$1" in
            -n|--lines)
                lines="${2:-100}"
                shift 2
                ;;
            --no-follow)
                follow="false"
                shift
                ;;
            *)
                die "Unknown logs option: $1"
                ;;
        esac
    done

    ensure_dirs
    touch "$RUNTIME_LOG"

    if [ "$follow" = "true" ]; then
        tail -n "$lines" -f "$RUNTIME_LOG"
    else
        tail -n "$lines" "$RUNTIME_LOG"
    fi
}

main() {
    local command="${1:-help}"
    shift || true

    case "$command" in
        start)
            start_service "$@"
            ;;
        stop|kill)
            stop_service "$@"
            ;;
        restart)
            stop_service || true
            start_service "$@"
            ;;
        status)
            status_service
            ;;
        logs|log)
            show_logs "$@"
            ;;
        help|-h|--help)
            usage
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
