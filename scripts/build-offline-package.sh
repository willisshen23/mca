#!/usr/bin/env bash
#
# 一键生成麒麟 V10 / Linux x86_64 完整离线部署包。
# 请在联网的 Linux x86_64 构建机上执行：
#   bash scripts/build-offline-package.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_PYTHON="${BUILD_PYTHON:-python3.12}"
PYTHON_ARCHIVE_NAME="cpython-3.12.13-x86_64-linux-gnu.tar.gz"
PYTHON_ARCHIVE_URL="${PYTHON_ARCHIVE_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20260623/cpython-3.12.13%2B20260623-x86_64-unknown-linux-gnu-install_only.tar.gz}"
PACKAGE_NAME="${PACKAGE_NAME:-activity-analysis-assistant-offline-$(date +%Y%m%d-%H%M%S).tar.gz}"
PACKAGE_PATH="$ROOT_DIR/$PACKAGE_NAME"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/activity-analysis-offline-build.XXXXXX")"
STAGE_DIR="$BUILD_ROOT/activity-analysis-assistant"
BUILD_VENV="$BUILD_ROOT/build-venv"

cleanup() {
    rm -rf "$BUILD_ROOT"
}
trap cleanup EXIT

fail() {
    echo "错误: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "缺少命令: $1"
}

[ "$(uname -s)" = "Linux" ] || fail "必须在 Linux x86_64 构建机执行，确保离线依赖与麒麟兼容"
[ "$(uname -m)" = "x86_64" ] || fail "构建机架构必须是 x86_64"

require_command "$BUILD_PYTHON"
require_command npm
require_command tar
require_command sha256sum
require_command gzip
require_command xargs

echo ">>> [1/5] 构建前端"
cd "$ROOT_DIR/frontend"
npm ci
npm run build
[ -f "$ROOT_DIR/frontend/dist/index.html" ] || fail "前端构建产物缺少 dist/index.html"

echo ">>> [2/5] 准备部署目录"
mkdir -p "$STAGE_DIR"
cp -a "$ROOT_DIR/backend" "$STAGE_DIR/backend"
cp -a "$ROOT_DIR/ops" "$STAGE_DIR/ops"
rm -rf "$STAGE_DIR/ops/data" "$STAGE_DIR/ops/__pycache__" \
    "$STAGE_DIR/ops/src/__pycache__" "$STAGE_DIR/ops/tests/__pycache__"
rm -f "$STAGE_DIR/ops/.env"
mkdir -p "$STAGE_DIR/data"
cp -a "$ROOT_DIR/data/mysql" "$STAGE_DIR/data/mysql"
rm -rf "$STAGE_DIR/backend/venv" "$STAGE_DIR/backend/.env" "$STAGE_DIR/backend/data"
rm -rf "$STAGE_DIR/backend/src/static"
cp -a "$ROOT_DIR/frontend/dist" "$STAGE_DIR/backend/src/static"
cp "$ROOT_DIR/deploy-offline.sh" "$STAGE_DIR/deploy-offline.sh"
mkdir -p "$STAGE_DIR/offline-bundle/python" \
    "$STAGE_DIR/offline-bundle/wheels"

echo ">>> [3/5] 准备便携 Python"
PYTHON_ARCHIVE_SOURCE="$ROOT_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME"
PYTHON_ARCHIVE_TARGET="$STAGE_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME"
if [ -f "$PYTHON_ARCHIVE_SOURCE" ]; then
    cp "$PYTHON_ARCHIVE_SOURCE" "$PYTHON_ARCHIVE_TARGET"
else
    require_command curl
    curl -fL --retry 3 -o "$PYTHON_ARCHIVE_TARGET" "$PYTHON_ARCHIVE_URL"
fi
gzip -t "$PYTHON_ARCHIVE_TARGET"

echo ">>> [4/5] 下载全部 Python 离线依赖"
"$BUILD_PYTHON" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
"$BUILD_VENV/bin/python" -m pip download \
    --only-binary=:all: \
    --platform manylinux2014_x86_64 \
    --platform manylinux_2_17_x86_64 \
    --platform manylinux_2_28_x86_64 \
    --python-version 312 \
    --implementation cp \
    --abi cp312 \
    --dest "$STAGE_DIR/offline-bundle/wheels" \
    -r "$ROOT_DIR/backend/requirements-offline.txt"

echo ">>> [5/5] 生成校验清单并打包"
(
    cd "$STAGE_DIR/offline-bundle"
    find python wheels -type f -print0 \
        | sort -z \
        | xargs -0 sha256sum > MANIFEST.sha256
)
chmod +x "$STAGE_DIR/deploy-offline.sh" "$STAGE_DIR/backend/scripts/"*.sh
tar -C "$BUILD_ROOT" -czf "$PACKAGE_PATH" activity-analysis-assistant

echo ""
echo "离线部署包已生成:"
echo "  $PACKAGE_PATH"
echo ""
echo "目标机只需解压后执行一次:"
echo "  bash deploy-offline.sh"
