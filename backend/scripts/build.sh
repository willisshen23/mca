#!/usr/bin/env bash
#
# build.sh — 构建前端并打包为离线部署产物
# 在有网络环境的开发机上运行
#
# 可选环境变量:
#   TARGET_PYTHON_VERSION  靶机 Python 版本 (如 310, 311, 312)，默认自动检测
#   TARGET_PLATFORM        靶机平台 (如 manylinux2014_x86_64, macosx_11_0_arm64)
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
echo "=== 项目根目录: $ROOT"

# 1. 构建前端
echo ""
echo ">>> [1/4] 构建前端..."
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
echo ">>> [2/4] 复制前端静态文件..."
STATIC_DIR="$ROOT/backend/src/infrastructure/static"
rm -rf "$STATIC_DIR"
cp -r "$ROOT/frontend/dist" "$STATIC_DIR"
echo "前端文件已复制到: $STATIC_DIR"
if [ ! -f "$STATIC_DIR/index.html" ]; then
    echo "错误: 静态文件复制失败"
    exit 1
fi

# 3. 下载 Python 离线包
echo ""
echo ">>> [3/4] 下载 Python 离线依赖包..."

WHEELS_DIR="$ROOT/backend/wheels"
mkdir -p "$WHEELS_DIR"
rm -f "$WHEELS_DIR"/*.whl

cd "$ROOT/backend"

# 收集 pip download 参数
PIP_EXTRA_ARGS=()
if [ -n "${TARGET_PYTHON_VERSION:-}" ]; then
    PIP_EXTRA_ARGS+=(--python-version "$TARGET_PYTHON_VERSION")
    echo "指定靶机 Python 版本: $TARGET_PYTHON_VERSION"
fi
if [ -n "${TARGET_PLATFORM:-}" ]; then
    PIP_EXTRA_ARGS+=(--platform "$TARGET_PLATFORM")
    echo "指定靶机平台: $TARGET_PLATFORM"
fi
if [ ${#PIP_EXTRA_ARGS[@]} -eq 0 ]; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}{sys.version_info.minor}')")
    echo "自动检测开发机 Python 版本: $PY_VER (如靶机版本不同，请设置 TARGET_PYTHON_VERSION)"
fi

pip download -r requirements.txt -d "$WHEELS_DIR" ${PIP_EXTRA_ARGS[@]+"${PIP_EXTRA_ARGS[@]}"} 2>&1 || {
    echo ""
    echo "警告: pip download 失败，将跳过离线包下载"
    echo "靶机需手动执行: pip install -r requirements.txt"
    echo "如因平台差异导致失败，尝试: TARGET_PYTHON_VERSION=310 TARGET_PLATFORM=manylinux2014_x86_64 bash scripts/build.sh"
}

WHEEL_COUNT=$(ls -1 "$WHEELS_DIR"/*.whl 2>/dev/null | wc -l)
echo "离线依赖包 ($WHEEL_COUNT 个) 已下载到: $WHEELS_DIR"

# 4. 打包
echo ""
echo ">>> [4/4] 打包部署产物..."
PACKAGE_NAME="activity-analysis-assistant-$(date +%Y%m%d-%H%M%S).tar.gz"
cd "$ROOT"
tar -czf "$PACKAGE_NAME" \
    --exclude='frontend/node_modules' \
    --exclude='frontend/dist' \
    --exclude='backend/__pycache__' \
    --exclude='backend/src/__pycache__' \
    --exclude='backend/.env' \
    --exclude='backend/data/uploads/*' \
    --exclude='backend/data/outputs/*' \
    --exclude='*.tar.gz' \
    --exclude='.git' \
    backend/ data/mysql/ frontend/package.json frontend/package-lock.json

PACKAGE_SIZE=$(ls -lh "$PACKAGE_NAME" | awk '{print $5}')
echo ""
echo "=== 构建完成 ==="
echo "部署包: $ROOT/$PACKAGE_NAME"
echo "大小:   $PACKAGE_SIZE"
echo ""
echo "部署步骤:"
echo "  1. scp $PACKAGE_NAME user@目标机:/opt/"
echo "  2. ssh user@目标机"
echo "  3. cd /opt && tar -xzf $PACKAGE_NAME"
echo "  4. cd backend && bash scripts/start.sh"
