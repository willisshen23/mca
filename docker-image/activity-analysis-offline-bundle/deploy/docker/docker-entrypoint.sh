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

# 数据库种子：镜像内置的初始数据（构建时由 build-offline-images.sh 打入）。
# 仅当数据卷中不存在同名文件时才拷贝，绝不覆盖已有运行数据。
SEED_DIR="${SEED_DIR:-/app/backend/seed-data}"
if [ -d "$SEED_DIR" ]; then
  for seed in "$SEED_DIR"/*.db; do
    [ -f "$seed" ] || continue
    base="$(basename "$seed")"
    if [ ! -f "$DATA_DIR/$base" ]; then
      echo "种子数据: 初始化 $base -> $DATA_DIR/$base"
      cp "$seed" "$DATA_DIR/$base"
    fi
  done
fi

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
