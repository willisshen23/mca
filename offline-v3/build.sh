#!/usr/bin/env bash
#
# openJiuwen 版离线部署包构建（麒麟 V10 / Linux x86_64 / Python 3.12）
# 宿主机（macOS）用法：
#   cd frontend && npm ci && npm run build
#   docker run --rm --platform linux/amd64 -v "$PWD":/workspace -w /workspace \
#     python:3.12-bookworm bash offline-v3/build.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
V3_DIR="$ROOT_DIR/offline-v3"
BUILD_PYTHON="${BUILD_PYTHON:-python3.12}"
PYTHON_ARCHIVE_NAME="cpython-3.12.13-x86_64-linux-gnu.tar.gz"
PYTHON_ARCHIVE_URL="${PYTHON_ARCHIVE_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20260623/cpython-3.12.13%2B20260623-x86_64-unknown-linux-gnu-install_only.tar.gz}"
PACKAGE_NAME="${PACKAGE_NAME:-activity-analysis-assistant-offline-$(date +%Y%m%d-%H%M%S).tar.gz}"
DIST_DIR="$V3_DIR/dist"
PACKAGE_PATH="$DIST_DIR/$PACKAGE_NAME"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/njbank-offline-v3-build.XXXXXX")"
STAGE_DIR="$BUILD_ROOT/activity-analysis-assistant"
BUILD_VENV="$BUILD_ROOT/build-venv"

cleanup() { rm -rf "$BUILD_ROOT"; }
trap cleanup EXIT

fail() { echo "错误: $*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "缺少命令: $1"; }

[ "$(uname -s)" = "Linux" ] || fail "必须在 Linux x86_64（或 linux/amd64 容器）执行"
[ "$(uname -m)" = "x86_64" ] || fail "构建机架构必须是 x86_64"
require_command "$BUILD_PYTHON"
require_command tar
require_command sha256sum
require_command gzip
require_command xargs

echo ">>> [1/5] 校验前端产物（本脚本不构建前端，请先在宿主机 npm run build）"
[ -f "$ROOT_DIR/frontend/dist/index.html" ] || \
    fail "缺少 frontend/dist/index.html，请先在宿主机执行: cd frontend && npm ci && npm run build"

echo ">>> [2/5] 准备部署目录"
mkdir -p "$STAGE_DIR" "$DIST_DIR" "$V3_DIR/wheels" "$V3_DIR/python"
tar -C "$ROOT_DIR" \
    --exclude='backend/venv' --exclude='backend/.env' --exclude='backend/data' \
    --exclude='backend/src/static' --exclude='*/__pycache__' \
    -cf - backend | tar -C "$STAGE_DIR" -xf -
tar -C "$ROOT_DIR" \
    --exclude='ops/data' --exclude='ops/.env' --exclude='*/__pycache__' \
    -cf - ops | tar -C "$STAGE_DIR" -xf -
mkdir -p "$STAGE_DIR/data"
cp -a "$ROOT_DIR/data/mysql" "$STAGE_DIR/data/mysql"
# 应用只挂载 backend/src/infrastructure/static（backend/src/main.py StaticFiles），
# 前端产物必须覆盖到该目录；src/static 无人服务，不要往那里拷
rm -rf "$STAGE_DIR/backend/src/infrastructure/static"
cp -a "$ROOT_DIR/frontend/dist" "$STAGE_DIR/backend/src/infrastructure/static"
cp "$ROOT_DIR/deploy-offline.sh" "$STAGE_DIR/deploy-offline.sh"
mkdir -p "$STAGE_DIR/offline-bundle/python" "$STAGE_DIR/offline-bundle/wheels"

echo ">>> [3/5] 准备便携 Python"
PYTHON_ARCHIVE_TARGET="$STAGE_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME"
if [ -f "$V3_DIR/python/$PYTHON_ARCHIVE_NAME" ]; then
    cp "$V3_DIR/python/$PYTHON_ARCHIVE_NAME" "$PYTHON_ARCHIVE_TARGET"
elif [ -f "$ROOT_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME" ]; then
    cp "$ROOT_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME" "$PYTHON_ARCHIVE_TARGET"
    cp "$ROOT_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME" "$V3_DIR/python/"
else
    require_command curl
    curl -fL --retry 3 -o "$PYTHON_ARCHIVE_TARGET" "$PYTHON_ARCHIVE_URL"
    cp "$PYTHON_ARCHIVE_TARGET" "$V3_DIR/python/"
fi
gzip -t "$PYTHON_ARCHIVE_TARGET"

echo ">>> [4/5] 下载全部 Python 离线依赖（openJiuwen 全量闭包）"
"$BUILD_PYTHON" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
# pip download 会跳过 dest 中已存在的同名文件，offline-v3/wheels 兼作本机缓存
"$BUILD_VENV/bin/python" -m pip download \
    --only-binary=:all: \
    --platform manylinux2014_x86_64 \
    --platform manylinux_2_17_x86_64 \
    --platform manylinux_2_28_x86_64 \
    --python-version 312 \
    --implementation cp \
    --abi cp312 \
    --dest "$V3_DIR/wheels" \
    -r "$V3_DIR/requirements.txt"
cp -a "$V3_DIR/wheels/." "$STAGE_DIR/offline-bundle/wheels/"

echo ">>> [5/5] 生成校验清单并打包"
(
    cd "$STAGE_DIR/offline-bundle"
    find python wheels -type f -print0 | sort -z | xargs -0 -r sha256sum > MANIFEST.sha256
)
chmod +x "$STAGE_DIR/deploy-offline.sh" "$STAGE_DIR/backend/scripts/"*.sh
tar -C "$BUILD_ROOT" -czf "$PACKAGE_PATH" activity-analysis-assistant

echo ""
echo "离线部署包已生成: $PACKAGE_PATH"
echo "wheels: $(find "$V3_DIR/wheels" -maxdepth 1 -name '*.whl' | wc -l | tr -d ' ') 个，$(du -sh "$V3_DIR/wheels" | cut -f1)"
echo "目标机只需解压后执行一次: bash deploy-offline.sh"
