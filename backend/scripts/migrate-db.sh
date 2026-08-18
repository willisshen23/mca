#!/usr/bin/env bash
#
# MySQL 协议兼容数据库部署入口。
#
# 用法：
#   bash backend/scripts/migrate-db.sh auto
#   bash backend/scripts/migrate-db.sh full
#   bash backend/scripts/migrate-db.sh upgrade
#
# 数据库迁移统一由离线环境自带的 PyMySQL 执行，不依赖系统 mysql 命令。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${ENV_FILE:-$BACKEND_DIR/.env}"
MODE="${1:-auto}"
PYTHON_MIGRATOR="$SCRIPT_DIR/migrate_db.py"

die() {
    printf '[database] 错误: %s\n' "$*" >&2
    exit 1
}

case "$MODE" in
    auto|full|upgrade) ;;
    *) die "不支持的模式: $MODE（可选 auto、full、upgrade）" ;;
esac

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ] && [ -x "$BACKEND_DIR/venv/bin/python" ]; then
    PYTHON_BIN="$BACKEND_DIR/venv/bin/python"
fi
if [ -z "$PYTHON_BIN" ] && command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
fi

[ -n "$PYTHON_BIN" ] || die "找不到可用的 Python"
[ -f "$PYTHON_MIGRATOR" ] || die "缺少 PyMySQL 迁移器: $PYTHON_MIGRATOR"

printf '[database] 使用 PyMySQL 执行数据库部署\n'
exec env ENV_FILE="$ENV_FILE" "$PYTHON_BIN" "$PYTHON_MIGRATOR" "$MODE"
