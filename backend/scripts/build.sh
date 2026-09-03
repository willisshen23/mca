#!/usr/bin/env bash
#
# build.sh — 构建前端、编译后端字节码（pyc-only）并打包为离线部署产物
# 在有网络环境的开发机上运行
#
# 产物中业务代码（backend/src）只含 .pyc 字节码、不含 .py 源码，
# .pyc 严格绑定 Python minor 版本，靶机 Python 必须与 TARGET_PYTHON_VERSION 一致。
# 产物含种子数据库（skills.db / v3_checkpoints.db 的 sqlite3 .backup 一致性快照），
# 不含主密钥（backend/data/secrets）、.env、日志、上传/产出文件、测试与缓存。
#
# 可选环境变量:
#   TARGET_PYTHON_VERSION  靶机 Python 版本 (如 310, 311, 312)，默认 312
#   TARGET_PLATFORM        靶机平台，多个用空格分隔
#                          x86_64: manylinux2014_x86_64 manylinux_2_17_x86_64 manylinux_2_28_x86_64
#                          arm64:  manylinux2014_aarch64 manylinux_2_17_aarch64 manylinux_2_28_aarch64
#   TARGET_ARCH            靶机架构 amd64|arm64（用于包名后缀），
#                          默认按 TARGET_PLATFORM 推断，未指定时取本机架构
#   COMPILE_PYTHON         字节码编译用解释器，默认 python3.12，
#                          其 minor 版本必须与 TARGET_PYTHON_VERSION 一致
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
echo "=== 项目根目录: $ROOT"

TARGET_PYTHON_VERSION="${TARGET_PYTHON_VERSION:-312}"
TARGET_PLATFORM="${TARGET_PLATFORM:-}"
TARGET_ARCH="${TARGET_ARCH:-}"
COMPILE_PYTHON="${COMPILE_PYTHON:-python3.12}"

if [ -z "$TARGET_ARCH" ]; then
    case "$TARGET_PLATFORM" in
        *aarch64*) TARGET_ARCH="arm64" ;;
        *x86_64*)  TARGET_ARCH="amd64" ;;
        *)         TARGET_ARCH="$(uname -m)"; [ "$TARGET_ARCH" = "aarch64" ] && TARGET_ARCH="arm64" ;;
    esac
fi
echo "=== 目标架构: $TARGET_ARCH  靶机 Python: $TARGET_PYTHON_VERSION"

STAGE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/activity-analysis-tar-build.XXXXXX")"
cleanup() { rm -rf "$STAGE_ROOT"; }
trap cleanup EXIT

# 1. 构建前端
echo ""
echo ">>> [1/5] 构建前端..."
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
    echo "安装前端依赖..."
    npm ci
fi
npm run build

if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
    echo "错误: 前端构建失败，未找到 dist/index.html"
    exit 1
fi
echo "前端构建完成"

# 2. 复制前端产物到后端 static 目录
# 应用只挂载 backend/src/infrastructure/static（src/main.py StaticFiles），
# src/static 为历史遗留目录、无人服务，不要往那里拷
echo ""
echo ">>> [2/5] 复制前端静态文件..."
STATIC_DIR="$ROOT/backend/src/infrastructure/static"
rm -rf "$STATIC_DIR"
cp -r "$ROOT/frontend/dist" "$STATIC_DIR"
echo "前端文件已复制到: $STATIC_DIR"
if [ ! -f "$STATIC_DIR/index.html" ]; then
    echo "错误: 静态文件复制失败"
    exit 1
fi

# 3. 下载 Python 离线包（按靶机架构/版本，下载到 backend/wheels 兼作本机缓存）
echo ""
echo ">>> [3/5] 下载 Python 离线依赖包..."

WHEELS_DIR="$ROOT/backend/wheels"
mkdir -p "$WHEELS_DIR"
rm -f "$WHEELS_DIR"/*.whl

cd "$ROOT/backend"

PIP_EXTRA_ARGS=(--only-binary=:all: --python-version "$TARGET_PYTHON_VERSION")
if [ -n "$TARGET_PLATFORM" ]; then
    for plat in $TARGET_PLATFORM; do
        PIP_EXTRA_ARGS+=(--platform "$plat")
    done
    echo "指定靶机平台: $TARGET_PLATFORM"
fi
echo "指定靶机 Python 版本: $TARGET_PYTHON_VERSION"

pip download -r requirements.txt -d "$WHEELS_DIR" ${PIP_EXTRA_ARGS[@]+"${PIP_EXTRA_ARGS[@]}"} 2>&1 || {
    echo ""
    echo "警告: pip download 失败，将跳过离线包下载"
    echo "靶机需手动执行: pip install -r requirements.txt"
    echo "示例（arm64 靶机）: TARGET_ARCH=arm64 TARGET_PLATFORM=\"manylinux2014_aarch64 manylinux_2_17_aarch64 manylinux_2_28_aarch64\" bash scripts/build.sh"
}

WHEEL_COUNT=$(ls -1 "$WHEELS_DIR"/*.whl 2>/dev/null | wc -l)
echo "离线依赖包 ($WHEEL_COUNT 个) 已下载到: $WHEELS_DIR"

# 4. 暂存到 staging 并编译字节码（剥离 .py 源码）
# 编译为原地删除源码，必须在 staging 副本上执行，切勿直接改工作区
echo ""
echo ">>> [4/5] 编译后端字节码（pyc-only）..."
mkdir -p "$STAGE_ROOT/pkg"
cp -a "$ROOT/backend" "$STAGE_ROOT/pkg/backend"
# 严禁入包：主密钥（密文方案要求与密文物理分离）、运行日志、本地环境、测试与缓存
rm -rf "$STAGE_ROOT/pkg/backend/venv" "$STAGE_ROOT/pkg/backend/.venv" \
    "$STAGE_ROOT/pkg/backend/.env" \
    "$STAGE_ROOT/pkg/backend/data/uploads" \
    "$STAGE_ROOT/pkg/backend/data/outputs" \
    "$STAGE_ROOT/pkg/backend/data/logs" \
    "$STAGE_ROOT/pkg/backend/data/secrets" \
    "$STAGE_ROOT/pkg/backend/logs" \
    "$STAGE_ROOT/pkg/backend/.pytest_cache" \
    "$STAGE_ROOT/pkg/backend/tests"
find "$STAGE_ROOT/pkg/backend" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE_ROOT/pkg" -name '.DS_Store' -delete 2>/dev/null || true
mkdir -p "$STAGE_ROOT/pkg/backend/data/uploads" "$STAGE_ROOT/pkg/backend/data/outputs"

# 种子数据：用 sqlite3 .backup 做一致性快照（服务运行中也不会拷出脏数据），
# 目标机解压后直接以该库启动，技能/模板配置不丢失
if command -v sqlite3 >/dev/null 2>&1; then
    for name in skills.db v3_checkpoints.db; do
        db="$ROOT/backend/data/$name"
        if [ -f "$db" ]; then
            echo "快照种子数据库: $name"
            rm -f "$STAGE_ROOT/pkg/backend/data/$name"
            sqlite3 "$db" ".backup '$STAGE_ROOT/pkg/backend/data/$name'"
        fi
    done
else
    echo "警告: 未找到 sqlite3，种子库为直接拷贝（服务写入中可能不一致）" >&2
fi
mkdir -p "$STAGE_ROOT/pkg/data" "$STAGE_ROOT/pkg/frontend"
cp -a "$ROOT/data/mysql" "$STAGE_ROOT/pkg/data/mysql"
cp "$ROOT/frontend/package.json" "$ROOT/frontend/package-lock.json" "$STAGE_ROOT/pkg/frontend/"

EXPECT_PYTHON_VERSION="$TARGET_PYTHON_VERSION" COMPILE_PYTHON="$COMPILE_PYTHON" \
    bash "$ROOT/scripts/compile-pyc.sh" "$STAGE_ROOT/pkg/backend/src"

# 5. 打包
echo ""
echo ">>> [5/5] 打包部署产物..."
PACKAGE_NAME="activity-analysis-assistant-${TARGET_ARCH}-$(date +%Y%m%d-%H%M%S).tar.gz"
tar -czf "$ROOT/$PACKAGE_NAME" -C "$STAGE_ROOT/pkg" \
    backend data frontend

PACKAGE_SIZE=$(ls -lh "$ROOT/$PACKAGE_NAME" | awk '{print $5}')
echo ""
echo "=== 构建完成 ==="
echo "部署包: $ROOT/$PACKAGE_NAME"
echo "架构:   $TARGET_ARCH (Python $TARGET_PYTHON_VERSION, pyc-only)"
echo "大小:   $PACKAGE_SIZE"
echo ""
echo "部署步骤:"
echo "  1. scp $PACKAGE_NAME user@目标机:/opt/"
echo "  2. ssh user@目标机"
echo "  3. cd /opt && tar -xzf $PACKAGE_NAME"
echo "  4. cd backend && bash scripts/start.sh"
echo ""
echo "注意: 产物为 pyc-only，靶机系统 Python 必须是 ${TARGET_PYTHON_VERSION:0:1}.${TARGET_PYTHON_VERSION:1}（与构建期 TARGET_PYTHON_VERSION=$TARGET_PYTHON_VERSION 一致）"
