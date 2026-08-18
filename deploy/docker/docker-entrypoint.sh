#!/bin/sh
set -eu

DATA_DIR="${DATA_DIR:-/app/backend/data}"
UVICORN_LOG_LEVEL="$(printf '%s' "${LOG_LEVEL:-info}" | tr '[:upper:]' '[:lower:]')"

case "$UVICORN_LOG_LEVEL" in
  critical|error|warning|info|debug|trace) ;;
  *)
    echo "错误: LOG_LEVEL=${LOG_LEVEL:-} 不受支持" >&2
    echo "可选值: CRITICAL、ERROR、WARNING、INFO、DEBUG、TRACE" >&2
    exit 1
    ;;
esac

mkdir -p \
  "$DATA_DIR/uploads" \
  "$DATA_DIR/outputs/exports" \
  "$DATA_DIR/logs"

echo "============================================"
echo "  活动分析助手 - Docker SQLite 部署"
echo "============================================"
echo "业务数据库: ${BUSINESS_DATABASE_URL:-sqlite:////app/backend/data/skills.db}"
echo "会话状态库: ${DB_PATH:-/app/backend/data/checkpoints.db}"
echo "服务端口: ${PORT:-8000}"
echo ""

# FastAPI lifespan 会根据 SQLAlchemy 模型创建并升级 SQLite 表。
# Docker SQLite 模式不执行 data/mysql 下的 MySQL 迁移脚本。
exec python -m uvicorn src.main:app \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8000}" \
  --log-level "$UVICORN_LOG_LEVEL"
