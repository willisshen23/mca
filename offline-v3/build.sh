#!/usr/bin/env bash
#
# openJiuwen 版离线部署包构建（麒麟 V10 / Linux x86_64|arm64 / Python 3.12）
# 宿主机（macOS）用法：
#   cd frontend && npm ci && npm run build
#   docker run --rm --platform linux/amd64 -v "$PWD":/workspace -w /workspace \
#     python:3.12-bookworm bash offline-v3/build.sh
#
# 目标架构（.pyc、wheel 下载、便携 Python 均支持跨架构，x86_64 容器即可出 arm64 包）：
#   TARGET_ARCH=x86_64   # 默认，麒麟 V10 x86_64
#   TARGET_ARCH=aarch64  # 麒麟 V10 arm64（鲲鹏/飞腾等）
#   docker run --rm --platform linux/amd64 -e TARGET_ARCH=aarch64 \
#     -v "$PWD":/workspace -w /workspace \
#     python:3.12-bookworm bash offline-v3/build.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
V3_DIR="$ROOT_DIR/offline-v3"
BUILD_PYTHON="${BUILD_PYTHON:-python3.12}"
TARGET_ARCH="${TARGET_ARCH:-$(uname -m)}"

case "$TARGET_ARCH" in
    x86_64)
        PYTHON_ARCHIVE_NAME="cpython-3.12.13-x86_64-linux-gnu.tar.gz"
        PYTHON_ARCHIVE_URL="${PYTHON_ARCHIVE_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20260623/cpython-3.12.13%2B20260623-x86_64-unknown-linux-gnu-install_only.tar.gz}"
        WHEEL_PLATFORMS=(manylinux2014_x86_64 manylinux_2_17_x86_64 manylinux_2_28_x86_64)
        WHEELS_CACHE="$V3_DIR/wheels"
        ARCH_SUFFIX="amd64"
        ;;
    aarch64|arm64)
        TARGET_ARCH="aarch64"
        PYTHON_ARCHIVE_NAME="cpython-3.12.13-aarch64-linux-gnu.tar.gz"
        PYTHON_ARCHIVE_URL="${PYTHON_ARCHIVE_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20260623/cpython-3.12.13%2B20260623-aarch64-unknown-linux-gnu-install_only.tar.gz}"
        WHEEL_PLATFORMS=(manylinux2014_aarch64 manylinux_2_17_aarch64 manylinux_2_28_aarch64)
        WHEELS_CACHE="$V3_DIR/wheels-aarch64"
        ARCH_SUFFIX="arm64"
        ;;
    *) echo "错误: TARGET_ARCH 仅支持 x86_64 或 aarch64，当前值: $TARGET_ARCH" >&2; exit 1 ;;
esac

PACKAGE_NAME="${PACKAGE_NAME:-activity-analysis-assistant-offline-${ARCH_SUFFIX}-$(date +%Y%m%d-%H%M%S).tar.gz}"
DIST_DIR="$V3_DIR/dist"
PACKAGE_PATH="$DIST_DIR/$PACKAGE_NAME"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/activity-analysis-offline-v3-build.XXXXXX")"
STAGE_DIR="$BUILD_ROOT/activity-analysis-assistant"
BUILD_VENV="$BUILD_ROOT/build-venv"

cleanup() { rm -rf "$BUILD_ROOT"; }
trap cleanup EXIT

fail() { echo "错误: $*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "缺少命令: $1"; }

[ "$(uname -s)" = "Linux" ] || fail "必须在 Linux（或 linux/amd64 容器）执行"
require_command "$BUILD_PYTHON"
require_command tar
require_command sha256sum
require_command gzip
require_command xargs

echo ">>> 目标架构: $TARGET_ARCH（构建机: $(uname -m)，wheel/便携 Python/pyc 均跨架构获取）"

echo ">>> [1/6] 校验前端产物（本脚本不构建前端，请先在宿主机 npm run build）"
[ -f "$ROOT_DIR/frontend/dist/index.html" ] || \
    fail "缺少 frontend/dist/index.html，请先在宿主机执行: cd frontend && npm ci && npm run build"

echo ">>> [2/6] 准备部署目录"
mkdir -p "$STAGE_DIR" "$DIST_DIR" "$WHEELS_CACHE" "$V3_DIR/python"
tar -C "$ROOT_DIR" \
    --exclude='backend/venv' --exclude='backend/.env' --exclude='backend/data' \
    --exclude='backend/src/static' --exclude='backend/wheels' --exclude='*/__pycache__' \
    -cf - backend | tar -C "$STAGE_DIR" -xf -
mkdir -p "$STAGE_DIR/data"
cp -a "$ROOT_DIR/data/mysql" "$STAGE_DIR/data/mysql"
# 应用只挂载 backend/src/infrastructure/static（backend/src/main.py StaticFiles），
# 前端产物必须覆盖到该目录；src/static 无人服务，不要往那里拷
rm -rf "$STAGE_DIR/backend/src/infrastructure/static"
cp -a "$ROOT_DIR/frontend/dist" "$STAGE_DIR/backend/src/infrastructure/static"
cp "$ROOT_DIR/deploy-offline.sh" "$STAGE_DIR/deploy-offline.sh"
mkdir -p "$STAGE_DIR/offline-bundle/python" "$STAGE_DIR/offline-bundle/wheels"

echo ">>> [3/6] 编译业务代码字节码（pyc-only，剥离 .py 源码）"
# .pyc 与 CPU 架构无关，用构建容器内 Python 3.12 编译即可同时服务两种架构；
# 运维脚本 backend/scripts/*.py 保留源码（migrate-db.sh 运行期要执行）。
# （ops/ 目录已于 e863bfe 移除，不再参与打包）
COMPILE_PYTHON="$BUILD_PYTHON" EXPECT_PYTHON_VERSION=312 \
    bash "$ROOT_DIR/scripts/compile-pyc.sh" \
        "$STAGE_DIR/backend/src"

echo ">>> [4/6] 准备便携 Python ($TARGET_ARCH)"
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

echo ">>> [5/6] 下载全部 Python 离线依赖（openJiuwen 全量闭包，$TARGET_ARCH）"
"$BUILD_PYTHON" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
# pip download 会跳过 dest 中已存在的同名文件，wheels 缓存目录按架构隔离（兼作本机缓存）
PIP_PLATFORM_ARGS=()
for plat in "${WHEEL_PLATFORMS[@]}"; do
    PIP_PLATFORM_ARGS+=(--platform "$plat")
done
"$BUILD_VENV/bin/python" -m pip download \
    --only-binary=:all: \
    "${PIP_PLATFORM_ARGS[@]}" \
    --python-version 312 \
    --implementation cp \
    --abi cp312 \
    --dest "$WHEELS_CACHE" \
    -r "$V3_DIR/requirements.txt"
cp -a "$WHEELS_CACHE/." "$STAGE_DIR/offline-bundle/wheels/"

echo ">>> [6/6] 生成校验清单并打包"
(
    cd "$STAGE_DIR/offline-bundle"
    find python wheels -type f -print0 | sort -z | xargs -0 -r sha256sum > MANIFEST.sha256
)
chmod +x "$STAGE_DIR/deploy-offline.sh" "$STAGE_DIR/backend/scripts/"*.sh
tar -C "$BUILD_ROOT" -czf "$PACKAGE_PATH" activity-analysis-assistant

echo ""
echo "离线部署包已生成: $PACKAGE_PATH"
echo "架构: $TARGET_ARCH（包名后缀 $ARCH_SUFFIX）"
echo "wheels: $(find "$WHEELS_CACHE" -maxdepth 1 -name '*.whl' | wc -l | tr -d ' ') 个，$(du -sh "$WHEELS_CACHE" | cut -f1)"
echo "目标机只需解压后执行一次: bash deploy-offline.sh"
